"""P0 修复测试。

- #4 start_instance 去重竞态：Redis SETNX 抢占锁（重复拒绝 / 不同 inputs 放行 / Redis 不可用降级 DB）
- #5 json.loads 异常处理：execute_workflow 参数 JSON 畸形时写 failed 终态（_mark_instance_failed 的 CAS 语义）
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import redis
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

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
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
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
        self.assertEqual(instance.status, "running")
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
            patch.object(workflow_tasks, "_async_execute") as mock_async,
        ):
            # apply 同步执行 Celery task（不经 broker），bind=True 自动注入 self
            workflow_tasks.execute_workflow.apply(args=(instance.id, definition.id, "{bad json"))
        mock_mark.assert_called_once()
        self.assertIn("解析失败", mock_mark.call_args.args[1])
        mock_async.assert_not_called()  # 参数解析失败，不应走到真正执行

    def test_valid_json_proceeds_to_execute(self):
        """正常 JSON 路径仍进入 _async_execute（保证修复未误伤正常流程）。"""
        with patch.object(workflow_tasks, "_async_execute", AsyncMock()) as mock_async:
            workflow_tasks.execute_workflow.apply(args=(999, 1, '{"q": "hi"}'))
        mock_async.assert_called_once()


if __name__ == "__main__":
    unittest.main()
