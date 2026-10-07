"""二期 B2：node_start/node_done custom 事件 + async_execute 双形态流的回归锁定。

验证点（WF-P1-6 / WF-P2-15）：
- node_start 推进 instance.current_node（CAS running 防覆盖终态）并广播 SSE；
- node_done 的真实 latency 经关联 dict 落入 WorkflowExecutionLog，缺失时回退事件间隔；
- 元组事件形态下 __interrupt__ 仍走 updates 通道 → paused；
- 超时归因文案变为「当前执行节点」；
- 未知 custom / 非元组事件被忽略不炸。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_stream_events.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.tasks import workflow_tasks


class _BaseStreamTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.definition = WorkflowDefinition(
            code="wf1", name="WF1", graph_json="{}", is_active=True, current_version_id=1, user_id=1
        )
        self.session.add(self.definition)
        self.session.commit()
        self.session.refresh(self.definition)

    def tearDown(self):
        self.session.close()

    def _add_instance(self, status: str = "running") -> WorkflowInstance:
        instance = WorkflowInstance(
            definition_id=self.definition.id,
            thread_id="t1",
            status=status,
            state_data="{}",
            user_id=1,
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def _run(self, instance: WorkflowInstance, *, events=None, graph_json=None, published=None):
        """驱动 async_execute（fake 编译器 + 全套旁路 patch），返回 published 收集器。"""
        published = published if published is not None else []

        fake_events = events if events is not None else []

        class _FakeCompiled:
            def __init__(self, checkpointer):
                self.checkpointer = checkpointer

            def astream(self, state, config=None, stream_mode=None):
                async def _gen():
                    for ev in fake_events:
                        yield ev

                return _gen()

        class _FakeGraph:
            def compile(self, checkpointer=None):
                return _FakeCompiled(checkpointer)

        class _FakeCompiler:
            @staticmethod
            def compile_graph(graph_json_):
                return _FakeGraph()

        @asynccontextmanager
        async def fake_cm():
            yield object()

        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event", side_effect=lambda *a: published.append(a)),
            patch.object(workflow_tasks, "persist_workflow_artifacts"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "WorkflowCompiler", _FakeCompiler),
            patch.object(workflow_tasks, "get_async_checkpointer", fake_cm),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id,
                    self.definition.id,
                    {"q": 1},
                    None,
                    graph_json_override=graph_json or {"nodes": [], "edges": []},
                )
            )
        return published


class NodeStartAdvancesCurrentNodeTestCase(_BaseStreamTestCase):
    def test_node_start_writes_current_node_and_publishes(self):
        instance = self._add_instance()
        graph = {"nodes": [{"id": "n1", "type": "llm", "name": "节点一"}], "edges": []}
        events = [
            ("custom", {"type": "node_start", "node_id": "n1", "status": "running"}),
            ("custom", {"type": "node_done", "node_id": "n1", "status": "done", "latency_ms": 1234}),
            ("updates", {"n1": {"variables": {"a": 1}}}),
        ]
        published = self._run(instance, events=events, graph_json=graph)

        with Session(self.engine) as verify:
            row = verify.get(WorkflowInstance, instance.id)
            self.assertEqual(row.status, "success")
            self.assertEqual(row.current_node, "n1", "node_start 应即时推进 current_node")

        event_names = [name for _, name, *_ in published]
        self.assertIn("node_start", event_names)
        self.assertIn("node_done", event_names)
        self.assertIn("node_update", event_names)

    def test_node_start_cas_spares_cancelled_terminal(self):
        """执行中途被取消：node_start 的 CAS（status=='running'）不得覆盖 cancelled 终态。"""
        instance = self._add_instance(status="running")
        test_engine = self.engine  # 内嵌类无法捕获 self，先取局部引用

        class _CancellingCompiled:
            def __init__(self, checkpointer):
                self.checkpointer = checkpointer

            def astream(self, state, config=None, stream_mode=None):
                async def _gen():
                    # 产 node_start 前先把实例翻成 cancelled（模拟执行中取消）
                    with Session(test_engine) as s:
                        s.get(WorkflowInstance, instance.id).status = "cancelled"
                        s.commit()
                    yield ("custom", {"type": "node_start", "node_id": "n1", "status": "running"})
                    yield ("updates", {"n1": {"variables": {}}})

                return _gen()

        class _FakeGraph:
            def compile(self, checkpointer=None):
                return _CancellingCompiled(checkpointer)

        class _FakeCompiler:
            @staticmethod
            def compile_graph(graph_json_):
                return _FakeGraph()

        published = []
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event", side_effect=lambda *a: published.append(a)),
            patch.object(workflow_tasks, "persist_workflow_artifacts"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "WorkflowCompiler", _FakeCompiler),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id,
                    self.definition.id,
                    {"q": 1},
                    None,
                    graph_json_override={"nodes": [{"id": "n1", "type": "llm", "name": "N1"}], "edges": []},
                )
            )

        with Session(self.engine) as verify:
            row = verify.get(WorkflowInstance, instance.id)
            self.assertEqual(row.status, "cancelled", "终态不得被 node_start 覆盖")
            self.assertIsNone(row.current_node, "cancelled 实例的 current_node 不得被推进")


class NodeDoneLatencyTestCase(_BaseStreamTestCase):
    def test_latency_from_node_done_custom_event(self):
        instance = self._add_instance()
        graph = {"nodes": [{"id": "n1", "type": "llm", "name": "节点一"}], "edges": []}
        events = [
            ("custom", {"type": "node_done", "node_id": "n1", "status": "done", "latency_ms": 1234}),
            ("updates", {"n1": {"variables": {"a": 1}}}),
        ]
        self._run(instance, events=events, graph_json=graph)

        from sqlmodel import select

        with Session(self.engine) as verify:
            log_row = verify.exec(
                select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == instance.id)
            ).first()
        self.assertIsNotNone(log_row)
        self.assertEqual(log_row.latency_ms, 1234, "node_done 携带的真实耗时应落日志行")

    def test_latency_falls_back_to_interval_without_custom(self):
        """无 custom 事件（存量 fake / 异常路径）时回退事件间隔计算，仍为非负 int。"""
        instance = self._add_instance()
        graph = {"nodes": [{"id": "n1", "type": "llm", "name": "节点一"}], "edges": []}
        events = [("updates", {"n1": {"variables": {"a": 1}}})]
        self._run(instance, events=events, graph_json=graph)

        from sqlmodel import select

        with Session(self.engine) as verify:
            log_row = verify.exec(
                select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == instance.id)
            ).first()
        self.assertIsNotNone(log_row)
        self.assertIsInstance(log_row.latency_ms, int)
        self.assertGreaterEqual(log_row.latency_ms, 0)


class InterruptStillPausedInTupleFormTestCase(_BaseStreamTestCase):
    def test_interrupt_in_tuple_form_marks_paused(self):
        """元组事件形态下 __interrupt__ 仍走 updates 通道 → paused 终态。"""
        instance = self._add_instance()
        graph = {"nodes": [{"id": "hi", "type": "human_input", "name": "审批"}], "edges": []}
        events = [
            ("custom", {"type": "node_start", "node_id": "hi", "status": "running"}),
            ("updates", {"__interrupt__": (object(),)}),
        ]
        published = self._run(instance, events=events, graph_json=graph)

        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "paused")
        event_names = [name for _, name, *_ in published]
        self.assertIn("paused", event_names)
        self.assertIn("node_start", event_names)


class MalformedEventsIgnoredTestCase(_BaseStreamTestCase):
    def test_unknown_custom_and_non_tuple_events_ignored(self):
        instance = self._add_instance()
        graph = {"nodes": [{"id": "n1", "type": "llm", "name": "N1"}], "edges": []}
        events = [
            ("custom", {"foo": 1}),  # 无 type 的未知 custom
            ("custom", "not-a-dict"),  # 非 dict payload
            "not-a-tuple",  # 非元组形态（污染注入）
            ("updates", {"n1": {"variables": {"a": 1}}}),
        ]
        published = self._run(instance, events=events, graph_json=graph)

        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "success")
        event_names = [name for _, name, *_ in published]
        self.assertNotIn("node_start", event_names)
        self.assertNotIn("node_done", event_names)


class TimeoutAttributionTestCase(_BaseStreamTestCase):
    def test_timeout_message_names_current_running_node(self):
        """超时归因：node_start 已推进 current_node，文案应为「当前执行节点」+ 节点名。"""
        instance = self._add_instance()
        graph = {"nodes": [{"id": "n1", "type": "llm", "name": "慢节点"}], "edges": []}

        class _SlowCompiled:
            def __init__(self, checkpointer):
                self.checkpointer = checkpointer

            def astream(self, state, config=None, stream_mode=None):
                async def _gen():
                    yield ("custom", {"type": "node_start", "node_id": "n1", "status": "running"})
                    await asyncio.sleep(5)  # 远超测试超时预算

                return _gen()

        class _FakeGraph:
            def compile(self, checkpointer=None):
                return _SlowCompiled(checkpointer)

        class _FakeCompiler:
            @staticmethod
            def compile_graph(graph_json_):
                return _FakeGraph()

        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "WorkflowCompiler", _FakeCompiler),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
            patch.object(settings, "WORKFLOW_NODE_TIMEOUT", 0.1),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id,
                    self.definition.id,
                    {"q": 1},
                    None,
                    graph_json_override=graph,
                )
            )

        with Session(self.engine) as verify:
            row = verify.get(WorkflowInstance, instance.id)
            self.assertEqual(row.status, "failed")
            self.assertEqual(row.failed_node_id, "n1")
            self.assertIn("当前执行节点", row.error_message)
            self.assertIn("慢节点", row.error_message)


if __name__ == "__main__":
    unittest.main()
