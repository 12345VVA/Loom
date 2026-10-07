"""三期 B7（WF-P2-17）：failed 实例断点续跑（有 checkpoint 前提）。

- 有可恢复 checkpoint 的 failed → resume 放行（CAS failed→running + 重投 Celery）；
- 无 checkpoint 的 failed（普通节点异常/超时失败）→ 409 引导重跑；
- 终态（success/cancelled）与 running/pending → 400 状态不符；paused 路径不回归。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_failed_resume.py -q
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.workflow_service import WorkflowInstanceService

_SVC_MODULE = "app.modules.workflow.service.workflow_service"
_TASKS_MODULE = "app.modules.workflow.tasks.workflow_tasks"


def _user(uid: int) -> User:
    return User(
        id=uid,
        username=f"u{uid}",
        full_name=f"u{uid}",
        password_hash="x",
        is_active=True,
        is_super_admin=False,
    )


class FailedResumeTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self, owner_uid: int = 1) -> WorkflowDefinition:
        definition = WorkflowDefinition(name="t", code=f"t-{owner_uid}-{uuid.uuid4().hex[:8]}", owner_id=owner_uid)
        self.session.add(definition)
        self.session.commit()
        return definition

    def _add_instance(self, definition: WorkflowDefinition, status: str, owner_uid: int = 1) -> WorkflowInstance:
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id=f"thread-{definition.id}-{status}",
            status=status,
            state_data="{}",
            user_id=owner_uid,
        )
        self.session.add(instance)
        self.session.commit()
        return instance

    def _resume(self, instance_id: int, uid: int = 1):
        svc = WorkflowInstanceService(self.session)
        with patch(f"{_TASKS_MODULE}.execute_workflow") as mock_exec:
            mock_exec.delay.return_value.id = "task-failed-resume"
            return svc.resume_instance(instance_id, "answer", _user(uid)), mock_exec

    def test_failed_with_checkpoint_resumes(self):
        """failed + 可恢复 checkpoint → 放行：CAS failed→running + 重投 Celery。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="failed")
        with patch(f"{_SVC_MODULE}._has_resumable_checkpoint", return_value=True):
            updated, mock_exec = self._resume(instance.id)
        self.assertEqual(updated.status, "running")
        self.assertEqual(updated.celery_task_id, "task-failed-resume")
        mock_exec.delay.assert_called_once()

    def test_failed_without_checkpoint_rejected_409(self):
        """failed + 无 checkpoint（普通异常/超时失败）→ 409 引导重跑，状态不变。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="failed")
        with patch(f"{_SVC_MODULE}._has_resumable_checkpoint", return_value=False):
            with self.assertRaises(HTTPException) as cm:
                self._resume(instance.id)
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("断点", str(cm.exception.detail))
        self.session.refresh(instance)
        self.assertEqual(instance.status, "failed")

    def test_failed_without_thread_id_rejected(self):
        """thread_id 为空（无 checkpoint 命名空间）→ 409。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="failed")
        instance.thread_id = ""
        self.session.add(instance)
        self.session.commit()
        with self.assertRaises(HTTPException) as cm:
            self._resume(instance.id)
        self.assertEqual(cm.exception.status_code, 409)

    def test_terminal_states_still_rejected_400(self):
        """success/cancelled 终态与 running → 400 状态不符（前置检查）。"""
        for status in ("success", "cancelled", "running"):
            with self.subTest(status=status):
                definition = self._add_definition()
                instance = self._add_instance(definition, status=status)
                with self.assertRaises(HTTPException) as cm:
                    self._resume(instance.id)
                self.assertEqual(cm.exception.status_code, 400)

    def test_paused_path_no_checkpoint_check_regression(self):
        """paused 路径不触发 checkpoint 预检（回归守护：原语义不变）。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, status="paused")
        with patch(f"{_SVC_MODULE}._has_resumable_checkpoint", side_effect=AssertionError("paused 不应预检")):
            updated, mock_exec = self._resume(instance.id)
        self.assertEqual(updated.status, "running")
        mock_exec.delay.assert_called_once()

    def test_has_resumable_checkpoint_degrades_to_false(self):
        """checkpointer 访问异常按「无断点」处理（安全侧拒绝）。"""
        from app.modules.workflow.service import workflow_service as ws

        with patch(
            "app.modules.workflow.service.checkpointer.get_checkpointer",
            side_effect=RuntimeError("boom"),
        ):
            self.assertFalse(ws._has_resumable_checkpoint("some-thread"))


if __name__ == "__main__":
    unittest.main()
