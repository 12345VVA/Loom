"""P0 修复测试。

- #4 start_instance 去重竞态：Redis SETNX 抢占锁（重复拒绝 / 不同 inputs 放行 / Redis 不可用降级 DB）
- #5 json.loads 异常处理：execute_workflow 参数 JSON 畸形时写 failed 终态（_mark_instance_failed 的 CAS 语义）
- P0-3 async checkpointer：进程级 setup 幂等跳过（连接仍每任务新建，setup 仅首轮执行）
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import redis
from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.core.config import settings
from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.checkpointer import get_async_checkpointer
from app.modules.workflow.service.workflow_service import WorkflowInstanceService
from app.modules.workflow.tasks import workflow_tasks


def _user(uid: int) -> User:
    return User(
        id=uid,
        username=f"u{uid}",
        full_name=f"u{uid}",
        password_hash="x",
        is_active=True,
    )


class _BaseDBTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self) -> WorkflowDefinition:
        # current_version_id 非 None 才能通过 start_instance 的发布校验
        definition = WorkflowDefinition(
            code="wf1",
            name="WF1",
            graph_json="{}",
            is_active=True,
            current_version_id=1,
            user_id=1,
        )
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        return definition

    def _add_instance(self, definition: WorkflowDefinition, status: str = "running") -> WorkflowInstance:
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id="t1",
            status=status,
            state_data="{}",
            user_id=1,
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance


# ==========================================
# #4：start_instance 去重竞态
# ==========================================


class StartInstanceDedupTestCase(_BaseDBTestCase):
    def _start(self, definition: WorkflowDefinition, inputs: dict) -> WorkflowInstance:
        svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value.id = "task-1"
            return svc.start_instance(definition.id, inputs, _user(1))

    def test_rejects_duplicate_within_window(self):
        """同 inputs 在锁窗口内第二次启动被 Redis SETNX 拒绝，且不产生重复实例。"""
        definition = self._add_definition()
        with patch("app.core.redis.redis_client") as mock_rc:
            mock_rc.set.side_effect = [True, False]  # 第一次抢锁成功，第二次失败
            self._start(definition, {"q": "a"})
            with self.assertRaises(HTTPException) as cm:
                self._start(definition, {"q": "a"})
        self.assertEqual(cm.exception.status_code, 400)

        # 仅创建一个实例（重复请求被拦截）
        rows = list(self.session.exec(select(WorkflowInstance)))
        self.assertEqual(len(rows), 1)

    def test_allows_different_inputs(self):
        """不同 inputs 各自放行，各自创建实例。"""
        definition = self._add_definition()
        with patch("app.core.redis.redis_client") as mock_rc:
            mock_rc.set.return_value = True
            self._start(definition, {"q": "a"})
            self._start(definition, {"q": "b"})
        rows = list(self.session.exec(select(WorkflowInstance)))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.state_data for r in rows}, {'{"q": "a"}', '{"q": "b"}'})

    def test_falls_back_to_db_when_redis_unavailable(self):
        """Redis 不可用时降级为 DB 查询兜底，不阻断正常启动。"""
        definition = self._add_definition()
        with patch("app.core.redis.redis_client") as mock_rc:
            mock_rc.set.side_effect = redis.exceptions.ConnectionError("no redis")
            instance = self._start(definition, {"q": "a"})
        # 两段式启动（WF-P1-7）：创建即 pending，执行体开跑时才 CAS 提升 running
        self.assertEqual(instance.status, "pending")
        # mock_rc.set 被调用过（尝试抢锁），但异常被降级吞掉
        mock_rc.set.assert_called_once()


# ==========================================
# #5：json.loads 异常处理（_mark_instance_failed）
# ==========================================


class MarkInstanceFailedTestCase(_BaseDBTestCase):
    def test_transitions_running_to_failed_and_publishes(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event") as mock_pub,
        ):
            workflow_tasks._mark_instance_failed(instance.id, "boom")
        # 用全新 session 读取，绕开 self.session 的 identity map 缓存
        with Session(self.engine) as verify:
            refreshed = verify.get(WorkflowInstance, instance.id)
        self.assertEqual(refreshed.status, "failed")
        self.assertIn("boom", refreshed.error_message)
        mock_pub.assert_called_once()
        self.assertEqual(mock_pub.call_args.args[1], "failed")

    def test_no_op_on_non_matching_status(self):
        """CAS 谓词只命中 running，cancelled 实例不被覆盖。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="cancelled")
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event") as mock_pub,
        ):
            workflow_tasks._mark_instance_failed(instance.id, "boom")
        with Session(self.engine) as verify:
            refreshed = verify.get(WorkflowInstance, instance.id)
        self.assertEqual(refreshed.status, "cancelled")
        self.assertIsNone(refreshed.error_message)
        mock_pub.assert_not_called()


class ExecuteWorkflowBadJsonTestCase(_BaseDBTestCase):
    def test_bad_json_marks_failed_and_skips_execution(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        with (
            patch.object(workflow_tasks, "_mark_instance_failed") as mock_mark,
            patch.object(workflow_tasks, "async_execute") as mock_async,
        ):
            # apply 同步执行 Celery task（不经 broker），bind=True 自动注入 self
            workflow_tasks.execute_workflow.apply(args=(instance.id, definition.id, "{bad json"))
        mock_mark.assert_called_once()
        self.assertIn("解析失败", mock_mark.call_args.args[1])
        mock_async.assert_not_called()  # 参数解析失败，不应走到真正执行

    def test_valid_json_proceeds_to_execute(self):
        """正常 JSON 路径仍进入 async_execute（保证修复未误伤正常流程）。"""
        with patch.object(workflow_tasks, "async_execute", AsyncMock()) as mock_async:
            workflow_tasks.execute_workflow.apply(args=(999, 1, '{"q": "hi"}'))
        mock_async.assert_called_once()


# ==========================================
# P0-3：async checkpointer 进程级 setup 幂等跳过
# ==========================================


class _FakeSaver:
    setup_calls = 0

    async def setup(self):
        _FakeSaver.setup_calls += 1


class AsyncCheckpointerSetupOnceTestCase(unittest.TestCase):
    """postgres backend 下同一进程内多次进入 get_async_checkpointer，setup 仅首轮执行。"""

    def setUp(self):
        import app.modules.workflow.service.checkpointer as ckpt_mod

        self._ckpt_mod = ckpt_mod
        self._orig_flag = ckpt_mod._async_setup_done
        ckpt_mod._async_setup_done = False
        _FakeSaver.setup_calls = 0

    def tearDown(self):
        self._ckpt_mod._async_setup_done = self._orig_flag

    def test_setup_runs_once_across_reentries(self):
        @asynccontextmanager
        async def fake_from_conn_string(conn_str):
            yield _FakeSaver()

        async def enter_twice():
            for _ in range(2):
                async with get_async_checkpointer() as saver:
                    self.assertIsInstance(saver, _FakeSaver)

        with (
            patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "postgres"),
            patch("app.core.database.DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db"),
            patch(
                "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.from_conn_string",
                fake_from_conn_string,
            ),
        ):
            asyncio.run(enter_twice())

        self.assertEqual(_FakeSaver.setup_calls, 1, "setup 应仅进程首轮执行一次")


# ==========================================
# P0-2：无中断节点的图跳过 checkpointer
# ==========================================


class _FakeCompiled:
    """记录 compile(checkpointer=...) 入参；astream 产出可配置事件后自然结束。"""

    events: list = []

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer
        type(self).compiled_instances.append(self)

    compiled_instances: list = []

    def astream(self, state, config=None, stream_mode=None):
        async def _gen():
            for ev in type(self).events:
                yield ev

        return _gen()


class _FakeCompiler:
    @staticmethod
    def compile_graph(graph_json):
        return _FakeGraph()


class _FakeGraph:
    def compile(self, checkpointer=None):
        return _FakeCompiled(checkpointer)


class CheckpointerSkipTestCase(_BaseDBTestCase):
    """P0-2 接线：无 human_input 图不挂 checkpointer；human_input / resume 路径强制挂载。"""

    def _run(self, graph_json: dict, resume_val=None, *, compiler=None, events=None):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")

        holder = {"saver": object(), "cm_calls": 0}

        @asynccontextmanager
        async def fake_cm():
            holder["cm_calls"] += 1
            yield holder["saver"]

        _FakeCompiled.compiled_instances = []
        _FakeCompiled.events = events or []
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event"),
            patch.object(workflow_tasks, "persist_workflow_artifacts"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "WorkflowCompiler", compiler or _FakeCompiler),
            patch.object(workflow_tasks, "get_async_checkpointer", fake_cm),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id, definition.id, {"q": 1}, resume_val, graph_json_override=graph_json
                )
            )
        return instance, holder

    def test_graph_without_interrupt_skips_checkpointer(self):
        instance, holder = self._run({"nodes": [{"id": "n1", "type": "llm"}], "edges": []})
        self.assertEqual(holder["cm_calls"], 0, "无中断节点的图不应创建 checkpointer")
        self.assertIsNone(_FakeCompiled.compiled_instances[0].checkpointer)
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "success")

    def test_graph_with_human_input_uses_checkpointer(self):
        graph = {"nodes": [{"id": "h", "type": "human_input"}], "edges": []}
        _, holder = self._run(graph)
        self.assertEqual(holder["cm_calls"], 1)
        self.assertIs(_FakeCompiled.compiled_instances[0].checkpointer, holder["saver"])

    def test_resume_forces_checkpointer_even_without_interrupt(self):
        graph = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
        _, holder = self._run(graph, resume_val={"answer": 1})
        self.assertEqual(holder["cm_calls"], 1, "恢复路径硬依赖断点，必须挂载 checkpointer")
        self.assertIs(_FakeCompiled.compiled_instances[0].checkpointer, holder["saver"])

    def test_interrupt_without_checkpointer_marks_failed_not_paused(self):
        """防呆：无 checkpointer 时收到 __interrupt__ 不得写 paused（无法恢复的假死），按 failed 收尾。"""

        class _InterruptCompiler:
            @staticmethod
            def compile_graph(graph_json):
                return _FakeGraph()

        instance, holder = self._run(
            {"nodes": [{"id": "n1", "type": "llm"}], "edges": []},
            compiler=_InterruptCompiler,
            events=[{"__interrupt__": (object(),)}],
        )
        self.assertEqual(holder["cm_calls"], 0)
        with Session(self.engine) as verify:
            refreshed = verify.get(WorkflowInstance, instance.id)
        self.assertEqual(refreshed.status, "failed", "未挂载断点时中断应按 failed 收尾而非 paused")
        self.assertIn("未挂载断点", refreshed.error_message)


class MemoryBackendGuardTestCase(unittest.TestCase):
    """P2 防呆：memory backend 下异步分支可用（langgraph-checkpoint 4.x 无 memory/aio 模块，
    AsyncMemorySaver import 会 ModuleNotFoundError）且 delete_thread 诚实短路（跨进程空转）。"""

    def test_async_memory_checkpointer_yields_inmemory_saver(self):
        from langgraph.checkpoint.memory import InMemorySaver

        async def _run():
            async with get_async_checkpointer() as saver:
                return saver

        with patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "memory"):
            saver = asyncio.run(_run())
        self.assertIsInstance(saver, InMemorySaver)
        # 4.x 统一 sync+async 接口：异步方法存在，暂停/恢复链路调用不 AttributeError
        self.assertTrue(hasattr(saver, "aget_tuple"))
        self.assertTrue(hasattr(saver, "delete_thread"))

    def test_delete_thread_best_effort_short_circuits_on_memory(self):
        from app.modules.workflow.service import checkpointer as cp

        original_warned = cp._memory_delete_warned
        cp._memory_delete_warned = False
        try:
            with (
                patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "memory"),
                patch.object(cp.logger, "warning") as mock_warn,
            ):
                # 返回 False（跨进程空转，不虚报成功）；告警只发一次防刷屏
                self.assertFalse(cp.delete_thread_best_effort("t-1"))
                self.assertFalse(cp.delete_thread_best_effort("t-2"))
            self.assertEqual(mock_warn.call_count, 1)
        finally:
            cp._memory_delete_warned = original_warned


if __name__ == "__main__":
    unittest.main()
