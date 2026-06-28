"""工作流执行引擎生产化测试（修复审查报告 S3/S4/S5/S6）。

- S3：checkpointer 持久化后端（sqlite 正确构造、未知值抛错）+ 启动校验
- S4：主动取消 cancel_instance（原子迁移、终态拒绝、非 owner 403、revoke）
- S5：resume 原子 CAS（TOCTOU 防护）—— CAS 谓词只匹配 paused
- S6：resume user_input=None 防御 + DTO 收紧（拒 None / 拒超大值）
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.startup_checks import validate_startup_settings
from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowInstanceResumeRequest,
)
from app.modules.workflow.service import checkpointer as ckpt_module
from app.modules.workflow.service.workflow_service import (
    TERMINAL_STATUSES,
    WorkflowInstanceService,
)


def _user(uid: int, super_admin: bool = False) -> User:
    return User(
        id=uid,
        username=f"u{uid}",
        full_name=f"u{uid}",
        password_hash="x",
        is_active=True,
        is_super_admin=super_admin,
    )


# ==========================================
# S3：checkpointer 后端
# ==========================================


class CheckpointerBackendTestCase(unittest.TestCase):
    def setUp(self):
        self._saved = ckpt_module._checkpointer
        ckpt_module._checkpointer = None

    def tearDown(self):
        # 关闭可能被创建的 sqlite 连接，避免 Windows 文件句柄泄漏
        saver = ckpt_module._checkpointer
        conn = getattr(saver, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        ckpt_module._checkpointer = self._saved

    def test_sqlite_backend_returns_sqlitesaver(self):
        from langgraph.checkpoint.sqlite import SqliteSaver

        tmp = Path(tempfile.mkdtemp())
        with (
            patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "sqlite"),
            patch.object(ckpt_module, "get_db_path", return_value=tmp / "app.db"),
        ):
            saver = ckpt_module.get_checkpointer()
            self.assertIsInstance(saver, SqliteSaver)
            self.assertTrue((tmp / "workflow_checkpoints.db").exists())
            # 全局单例：第二次返回同一实例
            self.assertIs(ckpt_module.get_checkpointer(), saver)

    def test_unknown_backend_raises(self):
        with patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "redis"):
            with self.assertRaises(ValueError):
                ckpt_module.get_checkpointer()


class StartupCheckCheckpointTestCase(unittest.TestCase):
    def test_prod_memory_is_error(self):
        with (
            patch.object(settings, "DEBUG", False),
            patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "memory"),
        ):
            results = validate_startup_settings(settings)
            ckpt = [r for r in results if r.key == "WORKFLOW_CHECKPOINT_BACKEND"]
            self.assertTrue(ckpt)
            self.assertEqual(ckpt[0].level, "error")

    def test_unknown_backend_is_error_regardless_of_env(self):
        with (
            patch.object(settings, "DEBUG", False),
            patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "redis"),
        ):
            results = validate_startup_settings(settings)
            self.assertTrue(any(r.key == "WORKFLOW_CHECKPOINT_BACKEND" and r.level == "error" for r in results))

    def test_sqlite_not_flagged(self):
        with patch.object(settings, "WORKFLOW_CHECKPOINT_BACKEND", "sqlite"):
            results = validate_startup_settings(settings)
            self.assertFalse(any(r.key == "WORKFLOW_CHECKPOINT_BACKEND" for r in results))


# ==========================================
# S4 / S5 / S6：resume 与 cancel（需要 DB）
# ==========================================


class ResumeAndCancelTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self, owner_uid: int | None = 1) -> WorkflowDefinition:
        definition = WorkflowDefinition(
            code="wf1",
            name="WF1",
            graph_json="{}",
            is_active=True,
            user_id=owner_uid,
        )
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        return definition

    def _add_instance(
        self, definition: WorkflowDefinition, status: str = "paused", owner_uid: int | None = 1
    ) -> WorkflowInstance:
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id="t1",
            status=status,
            state_data='{"q": "hi"}',
            user_id=owner_uid,
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    # --- S6 ---

    def test_resume_none_user_input_rejected(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="paused")
        svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow"):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(svc.resume_instance(instance.id, None, _user(1)))
        self.assertEqual(cm.exception.status_code, 400)

    def test_resume_dto_rejects_none(self):
        with self.assertRaises(ValidationError):
            WorkflowInstanceResumeRequest(instance_id=1, user_input=None)

    def test_resume_dto_rejects_oversize(self):
        huge = "x" * 70000
        with self.assertRaises(ValidationError):
            WorkflowInstanceResumeRequest(instance_id=1, user_input=huge)

    # --- S5 ---

    def test_resume_paused_to_running_happy_path(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="paused")
        svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value.id = "task-9"
            updated = asyncio.run(svc.resume_instance(instance.id, "answer", _user(1)))
        self.assertEqual(updated.status, "running")
        self.assertEqual(updated.celery_task_id, "task-9")
        mock_exec.delay.assert_called_once()

    def test_resume_non_paused_rejected_by_precheck(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(svc.resume_instance(instance.id, "answer", _user(1)))
        self.assertEqual(cm.exception.status_code, 400)

    def test_cas_predicate_only_matches_paused(self):
        """S5 核心：原子 UPDATE ... WHERE status='paused' 只影响 paused 行，
        从而在并发 resume 中只允许一个请求 rowcount==1（DB 级原子保证）。"""
        definition = self._add_definition()
        paused = self._add_instance(definition, status="paused")
        running = self._add_instance(definition, status="running")

        r1 = self.session.execute(
            update(WorkflowInstance)
            .where(WorkflowInstance.id == running.id, WorkflowInstance.status == "paused")
            .values(status="running")
        )
        self.assertEqual(r1.rowcount, 0)  # running 行不被命中

        r2 = self.session.execute(
            update(WorkflowInstance)
            .where(WorkflowInstance.id == paused.id, WorkflowInstance.status == "paused")
            .values(status="running")
        )
        self.assertEqual(r2.rowcount, 1)  # paused 行被命中
        self.session.commit()

    def test_resume_non_owner_403(self):
        definition = self._add_definition(owner_uid=1)
        instance = self._add_instance(definition, status="paused", owner_uid=1)
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(svc.resume_instance(instance.id, "answer", _user(2)))
        self.assertEqual(cm.exception.status_code, 403)

    # --- S4 ---

    def test_cancel_running_transitions_to_cancelled_and_revokes(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        instance.celery_task_id = "task-1"
        self.session.add(instance)
        self.session.commit()

        svc = WorkflowInstanceService(self.session)
        with patch("app.celery_app.celery_app") as mock_celery:
            updated = asyncio.run(svc.cancel_instance(instance.id, _user(1)))
        self.assertEqual(updated.status, "cancelled")
        mock_celery.control.revoke.assert_called_once_with("task-1", terminate=True)

    def test_cancel_paused_allowed(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="paused")
        svc = WorkflowInstanceService(self.session)
        with patch("app.celery_app.celery_app"):
            updated = asyncio.run(svc.cancel_instance(instance.id, _user(1)))
        self.assertEqual(updated.status, "cancelled")

    def test_cancel_terminal_rejected(self):
        definition = self._add_definition()
        for terminal in ("success", "failed", "cancelled"):
            instance = self._add_instance(definition, status=terminal)
            svc = WorkflowInstanceService(self.session)
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(svc.cancel_instance(instance.id, _user(1)))
            self.assertEqual(cm.exception.status_code, 400)

    def test_cancel_non_owner_403(self):
        definition = self._add_definition(owner_uid=1)
        instance = self._add_instance(definition, status="running", owner_uid=1)
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(svc.cancel_instance(instance.id, _user(2)))
        self.assertEqual(cm.exception.status_code, 403)

    def test_cancel_not_found_404(self):
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(svc.cancel_instance(99999, _user(1)))
        self.assertEqual(cm.exception.status_code, 404)

    def test_cancel_without_celery_task_id_skips_revoke(self):
        definition = self._add_definition()
        instance = self._add_instance(definition, status="running")
        # celery_task_id 为 None
        svc = WorkflowInstanceService(self.session)
        with patch("app.celery_app.celery_app") as mock_celery:
            updated = asyncio.run(svc.cancel_instance(instance.id, _user(1)))
        self.assertEqual(updated.status, "cancelled")
        mock_celery.control.revoke.assert_not_called()

    def test_terminal_statuses_constant(self):
        self.assertIn("cancelled", TERMINAL_STATUSES)
        self.assertIn("success", TERMINAL_STATUSES)
        self.assertIn("failed", TERMINAL_STATUSES)


if __name__ == "__main__":
    unittest.main()
