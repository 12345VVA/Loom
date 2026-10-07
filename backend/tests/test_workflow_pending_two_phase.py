"""WF-P1-7 pending 两段式启动 + WF-P2-20 success CAS rowcount 的回归锁定。

两段式：创建落 pending（段一）→ 执行体开跑 CAS pending→running（段二，
_promote_pending_to_running）。eval 直建 running / resume 已 running 的实例经
复查容错放行；排队中被取消/回收/删除的实例静默退出。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_pending_two_phase.py -q
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine
from sqlalchemy import update as sa_update
from sqlmodel import Session, SQLModel, select

from app.core.config import settings
from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
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
# 段一：创建即 pending
# ==========================================


class StartInstanceCreatesPendingTestCase(_BaseDBTestCase):
    def test_start_instance_creates_pending_with_task_id(self):
        definition = self._add_definition()
        with (
            patch("app.core.redis.redis_client") as mock_rc,
            patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec,
        ):
            mock_rc.set.return_value = True
            mock_exec.delay.return_value.id = "task-1"
            svc = WorkflowInstanceService(self.session)
            instance = svc.start_instance(definition.id, {"q": "a"}, _user(1))
        self.assertEqual(instance.status, "pending", "两段式段一：创建应落 pending（已入队待执行）")
        self.assertEqual(instance.celery_task_id, "task-1")

    def test_trial_instance_creates_pending(self):
        definition = self._add_definition()
        with (
            patch("app.core.redis.redis_client") as mock_rc,
            patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec,
        ):
            mock_rc.set.return_value = True
            mock_exec.delay.return_value.id = "task-2"
            svc = WorkflowInstanceService(self.session)
            instance = svc.start_trial_instance(definition.id, {"q": "b"}, _user(1))
        self.assertEqual(instance.status, "pending")


# ==========================================
# 段二：_promote_pending_to_running CAS 语义
# ==========================================


class PromotePendingToRunningTestCase(_BaseDBTestCase):
    def setUp(self):
        super().setUp()
        self.definition = self._add_definition()

    def _promote(self, instance_id: int) -> bool:
        # promote 读写模块级 engine，须指向测试引擎
        with patch.object(workflow_tasks, "engine", self.engine):
            return workflow_tasks._promote_pending_to_running(instance_id)

    def test_pending_promoted_to_running(self):
        instance = self._add_instance(self.definition, status="pending")
        self.assertTrue(self._promote(instance.id))
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "running")

    def test_running_instance_passes_through(self):
        """eval 直建 running 的实例：CAS 不命中 → 复查 running → 放行。"""
        instance = self._add_instance(self.definition, status="running")
        self.assertTrue(self._promote(instance.id))

    def test_cancelled_instance_rejected(self):
        instance = self._add_instance(self.definition, status="cancelled")
        self.assertFalse(self._promote(instance.id))
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "cancelled")

    def test_failed_instance_rejected(self):
        instance = self._add_instance(self.definition, status="failed")
        self.assertFalse(self._promote(instance.id))
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "failed")

    def test_missing_instance_rejected(self):
        self.assertFalse(self._promote(999999))


# ==========================================
# async_execute 的 promote 门
# ==========================================


class _FakeCompiled:
    compiled_instances: list = []

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer
        type(self).compiled_instances.append(self)

    def astream(self, state, config=None, stream_mode=None):
        async def _gen():
            for ev in type(self).events:
                yield ev

        return _gen()

    events: list = []


class _FakeGraph:
    def compile(self, checkpointer=None):
        return _FakeCompiled(checkpointer)


class _FakeCompiler:
    @staticmethod
    def compile_graph(graph_json):
        return _FakeGraph()


class AsyncExecutePromoteGateTestCase(_BaseDBTestCase):
    def _run(self, instance: WorkflowInstance, events=None):
        _FakeCompiled.compiled_instances = []
        _FakeCompiled.events = events or []
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event"),
            patch.object(workflow_tasks, "persist_workflow_artifacts"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "WorkflowCompiler", _FakeCompiler),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id,
                    instance.definition_id,
                    {"q": 1},
                    None,
                    graph_json_override={"nodes": [], "edges": []},
                )
            )

    def test_cancelled_before_start_skips_execution(self):
        """排队中被取消的实例：promote 拒绝 → 不编译不执行，状态保持 cancelled。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="cancelled")
        self._run(instance)
        self.assertEqual(_FakeCompiled.compiled_instances, [], "promote 拒绝后不得触达编译器")
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "cancelled")

    def test_running_instance_passes_gate_and_finishes(self):
        """eval 直建 running 的实例经复查放行，正常跑完置 success。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        # 二期事件形态：stream_mode=["updates","custom"] 下事件为 (mode, payload) 元组
        self._run(instance, events=[("updates", {"n1": {"variables": {"a": 1}}})])
        self.assertEqual(len(_FakeCompiled.compiled_instances), 1)
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "success")


# ==========================================
# JSON 畸形兜底覆盖 pending
# ==========================================


class BadJsonPendingMarksFailedTestCase(_BaseDBTestCase):
    def test_bad_json_marks_pending_failed(self):
        """JSON 解析先于 promote：pending 实例的畸形参数也必须落到 failed 终态。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="pending")
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "async_execute") as mock_async,
            patch.object(workflow_tasks, "publish_event"),
            patch.object(workflow_tasks, "_notify_workflow_failure"),
        ):
            workflow_tasks.execute_workflow.apply(args=(instance.id, definition.id, "{bad json"))
        mock_async.assert_not_called()
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "failed")

    def test_mark_failed_with_narrow_expected_spares_pending(self):
        """expected 显式收窄为 "running" 时，pending 不被覆盖（参数语义保留）。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="pending")
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event") as mock_publish,
        ):
            workflow_tasks._mark_instance_failed(instance.id, "boom", expected="running")
        mock_publish.assert_not_called()
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "pending")


# ==========================================
# 去重 DB 兜底覆盖 pending
# ==========================================


class DedupDbFallbackIncludesPendingTestCase(_BaseDBTestCase):
    def test_db_fallback_rejects_pending_duplicate(self):
        """Redis 不可用降级 DB 查询时，排队中的 pending 同参实例同样命中去重。"""
        definition = self._add_definition()
        self.session.add(
            WorkflowInstance(
                definition_id=definition.id,
                thread_id="t-queued",
                status="pending",
                state_data=json.dumps({"q": "a"}),
                user_id=1,
            )
        )
        self.session.commit()

        svc = WorkflowInstanceService(self.session)
        with (
            patch("app.core.redis.redis_client") as mock_rc,
            patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec,
        ):
            mock_rc.set.side_effect = Exception("redis unavailable")
            mock_exec.delay.return_value.id = "task-x"
            with self.assertRaises(HTTPException) as cm:
                svc.start_instance(definition.id, {"q": "a"}, _user(1))
        self.assertEqual(cm.exception.status_code, 400)


# ==========================================
# eval 超时收尾覆盖 pending
# ==========================================


class CancelEvalInstanceCoversPendingTestCase(_BaseDBTestCase):
    def test_pending_instance_cancelled_by_eval_timeout(self):
        from app.modules.workflow_eval.service import eval_orchestrator

        definition = self._add_definition()
        instance = self._add_instance(definition, status="pending")
        with patch.object(eval_orchestrator, "engine", self.engine):
            eval_orchestrator.cancel_eval_instance(instance.id)
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "cancelled")


# ==========================================
# WF-P2-20：success 终态 CAS rowcount 检查
# ==========================================


class SuccessCasRaceTestCase(_BaseDBTestCase):
    """get 之后、CAS 之前的极小窗口内状态被并发改走时，不得广播 success。"""

    def _run_with_race(self, final_status: str):
        """经 resolve_payload 钩子在 CAS 前一刻把状态并发改走（该调用位于 get 与 CAS 之间）。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        real_resolve = workflow_tasks.resolve_payload
        _FakeCompiled.compiled_instances = []
        _FakeCompiled.events = []  # 类属性跨测试残留防护：本用例空事件流，直达 success 收尾块

        def resolve_and_flip(state, ref):
            with Session(self.engine) as s:
                s.execute(
                    sa_update(WorkflowInstance).where(WorkflowInstance.id == instance.id).values(status=final_status)
                )
                s.commit()
            return real_resolve(state, ref)

        published: list[tuple] = []
        with (
            patch.object(workflow_tasks, "engine", self.engine),
            patch.object(workflow_tasks, "publish_event", side_effect=lambda *a: published.append(a)),
            patch.object(workflow_tasks, "persist_workflow_artifacts") as mock_persist,
            patch.object(workflow_tasks, "_notify_workflow_failure"),
            patch.object(workflow_tasks, "resolve_payload", new=resolve_and_flip),
            patch.object(workflow_tasks, "WorkflowCompiler", _FakeCompiler),
            patch.object(settings, "WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT", True),
        ):
            asyncio.run(
                workflow_tasks.async_execute(
                    instance.id,
                    definition.id,
                    {"q": 1},
                    None,
                    graph_json_override={"nodes": [], "edges": []},
                )
            )
        return instance, published, mock_persist

    def test_race_to_cancelled_publishes_cancelled_not_success(self):
        instance, published, mock_persist = self._run_with_race("cancelled")
        events = [args[1] for args in published]
        self.assertIn("cancelled", events)
        self.assertNotIn("success", events)
        mock_persist.assert_not_called()
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "cancelled")

    def test_race_to_failed_publishes_neither(self):
        instance, published, mock_persist = self._run_with_race("failed")
        events = [args[1] for args in published]
        self.assertNotIn("success", events)
        self.assertNotIn("cancelled", events)
        self.assertNotIn("failed", events)
        mock_persist.assert_not_called()
        with Session(self.engine) as verify:
            self.assertEqual(verify.get(WorkflowInstance, instance.id).status, "failed")


# ==========================================
# 守护：test_node 维持内联 running（不走两段式）
# ==========================================


class TestNodeKeepsInlineRunningStatusTestCase(_BaseDBTestCase):
    def test_node_instance_is_running_during_inline_execution(self):
        """test_node 无队列窗口：执行体运行时实例必须已是 running（防将来误改 pending）。"""
        import json as _json

        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
        from app.modules.workflow.service import compiler as compiler_mod

        graph = {
            "nodes": [
                {"id": "n1", "type": "llm", "name": "LLM", "config": {"modelProfileCode": "p1"}},
            ],
            "edges": [],
        }
        definition = WorkflowDefinition(code="wf1", name="WF1", is_active=True, draft_version_id=1, user_id=1)
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        self.session.add(
            WorkflowDefinitionVersion(
                definition_id=definition.id, version_no=1, status="draft", graph_json=_json.dumps(graph)
            )
        )
        self.session.commit()

        observed: dict = {}

        async def fake_standalone(node_id, node_type, config, mock_variables):
            # 执行体运行时刻：查询最新 test_node 实例的即时状态
            with Session(self.engine) as s:
                row = s.exec(
                    select(WorkflowInstance)
                    .where(WorkflowInstance.run_type == "test_node")
                    .order_by(WorkflowInstance.id.desc())
                ).first()
                observed["status_at_exec"] = row.status if row else None
            return {"out": 1}

        with (
            patch("app.core.redis.redis_client") as mock_rc,
            patch.object(compiler_mod.WorkflowCompiler, "run_node_standalone", new=fake_standalone),
        ):
            mock_rc.set.return_value = True
            svc = WorkflowInstanceService(self.session)
            resp = asyncio.run(svc.test_node(definition.id, "n1", {"q": 1}, None))
        self.assertEqual(observed["status_at_exec"], "running", "test_node 内联执行时实例应为 running 而非 pending")
        self.assertIsNone(resp.error)


if __name__ == "__main__":
    unittest.main()
