"""Phase 4 权限与越权安全修复测试。

覆盖：
- Task 4.1 (P0-15): TaskInvoker 方法白名单 - 私有方法拦截 + 非白名单服务拒绝
- Task 4.2 (P1-14): notification sender_id 防伪造 - current_user.id 覆盖客户端传入值
- Task 4.3 (P1-15): workflow_annotation 归属校验 - 非 owner 访问被拒 403
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


class TaskInvokerWhitelistTests(unittest.TestCase):
    """Task 4.1 (P0-15): TaskInvoker 方法白名单"""

    def setUp(self):
        from app.modules.task.service.task_invoker import TaskInvoker

        self.TaskInvoker = TaskInvoker
        # 保存原始白名单状态，避免影响其他测试
        self._original_allowed = set(TaskInvoker._allowed_services)

    def tearDown(self):
        self.TaskInvoker._allowed_services = self._original_allowed

    def test_private_method_rejected_with_403(self):
        """以 _ 开头的方法名被拒绝，返回 403"""
        with patch.object(self.TaskInvoker, "scan_services"):
            with self.assertRaises(HTTPException) as ctx:
                self.TaskInvoker.invoke("task.info:_secret_method")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("下划线", ctx.exception.detail)

    def test_non_whitelisted_service_rejected_with_403(self):
        """白名单启用后，非白名单服务路径被拒绝，返回 403"""
        self.TaskInvoker.register_allowed_services(["task.info:allowed_method"])
        with patch.object(self.TaskInvoker, "scan_services"):
            with self.assertRaises(HTTPException) as ctx:
                self.TaskInvoker.invoke("task.info:not_whitelisted")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("白名单", ctx.exception.detail)

    def test_whitelisted_service_passes_whitelist_check(self):
        """白名单内的服务路径通过白名单校验（后续因服务不存在而 ValueError，不是 403）"""
        self.TaskInvoker.register_allowed_services(["task.info:allowed_method"])
        with patch.object(self.TaskInvoker, "scan_services"):
            # 白名单通过，但服务不存在 → ValueError 而非 403
            with self.assertRaises(ValueError):
                self.TaskInvoker.invoke("task.info:allowed_method")

    def test_whitelist_disabled_when_empty(self):
        """白名单为空时不启用白名单校验（仅拦截私有方法）"""
        # 确保白名单为空
        self.TaskInvoker._allowed_services.clear()
        with patch.object(self.TaskInvoker, "scan_services"):
            # 非私有方法，白名单为空 → 通过白名单校验，因服务不存在 ValueError
            with self.assertRaises(ValueError):
                self.TaskInvoker.invoke("task.info:some_method")


class NotificationSenderIdTests(unittest.TestCase):
    """Task 4.2 (P1-14): notification sender_id 防伪造"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_sender_id_overridden_by_current_user(self):
        """客户端传入的 sender_id 被 current_user.id 覆盖"""
        from app.modules.notification.service.notification_service import NotificationMessageService

        mock_user = MagicMock()
        mock_user.id = 42

        payload = {
            "title": "安全测试通知",
            "content": "验证 sender_id 防伪造",
            "sender_id": 999,  # 客户端伪造的 sender_id
            "message_type": "business",
            "level": "info",
        }

        service = NotificationMessageService(self.session)
        entity = service.add(payload, current_user=mock_user)

        self.assertEqual(entity.sender_id, 42)
        self.assertNotEqual(entity.sender_id, 999)

    def test_sender_id_not_overridden_without_current_user(self):
        """无 current_user 时 sender_id 不被覆盖（保持向后兼容）"""
        from app.modules.notification.service.notification_service import NotificationMessageService

        payload = {
            "title": "无用户通知",
            "content": "验证无 current_user 时的行为",
            "sender_id": 555,
            "message_type": "business",
            "level": "info",
        }

        service = NotificationMessageService(self.session)
        entity = service.add(payload, current_user=None)

        self.assertEqual(entity.sender_id, 555)

    def test_sender_id_override_in_list_payload(self):
        """列表 payload 中每条都被覆盖为 current_user.id"""
        from app.modules.notification.service.notification_service import NotificationMessageService

        mock_user = MagicMock()
        mock_user.id = 77

        payloads = [
            {
                "title": "批量通知1",
                "content": "内容1",
                "sender_id": 111,
                "message_type": "business",
                "level": "info",
            },
            {
                "title": "批量通知2",
                "content": "内容2",
                "sender_id": 222,
                "message_type": "business",
                "level": "info",
            },
        ]

        service = NotificationMessageService(self.session)
        entities = service.add(payloads, current_user=mock_user)

        self.assertEqual(len(entities), 2)
        for entity in entities:
            self.assertEqual(entity.sender_id, 77)


class AnnotationOwnershipTests(unittest.TestCase):
    """Task 4.3 (P1-15): workflow_annotation 归属校验"""

    def setUp(self):
        # 确保模型在 create_all 之前已注册到 SQLModel.metadata
        from app.modules.workflow_annotation.model.annotation import WorkflowAnnotation  # noqa: F401
        from app.modules.workflow_eval.model.enum import CaseResultStatus
        from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun

        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # 创建一个属于 user_id=1 的评估运行
        self.session.add(WorkflowEvalRun(test_set_id=1, user_id=1))
        self.session.commit()
        self.session.add(
            WorkflowEvalCaseResult(
                eval_run_id=1,
                case_key="case_1",
                score=1.0,
                passed=True,
                latency_ms=10,
                status=CaseResultStatus.SUCCESS,
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def _make_user(self, user_id: int, is_super_admin: bool = False):
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_super_admin = is_super_admin
        return mock_user

    def test_non_owner_add_annotation_rejected_403(self):
        """非 owner 添加标注被拒绝 403"""
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        other_user = self._make_user(user_id=2, is_super_admin=False)
        payload = {"case_result_id": 1, "label": "pass"}

        with self.assertRaises(HTTPException) as ctx:
            WorkflowAnnotationService(self.session).add(payload, current_user=other_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_non_owner_compute_kappa_rejected_403(self):
        """非 owner 计算 kappa 被拒绝 403"""
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        other_user = self._make_user(user_id=2, is_super_admin=False)
        with self.assertRaises(HTTPException) as ctx:
            WorkflowAnnotationService(self.session).compute_kappa(1, current_user=other_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_add_annotation_succeeds(self):
        """owner 添加标注成功"""
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        owner = self._make_user(user_id=1, is_super_admin=False)
        payload = {"case_result_id": 1, "label": "pass"}
        entity = WorkflowAnnotationService(self.session).add(payload, current_user=owner)
        self.assertEqual(entity.case_result_id, 1)
        self.assertEqual(entity.label, "pass")
        self.assertEqual(entity.annotator_user_id, 1)

    def test_super_admin_bypasses_ownership_check(self):
        """超管绕过归属校验"""
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        super_admin = self._make_user(user_id=999, is_super_admin=True)
        payload = {"case_result_id": 1, "label": "fail"}
        entity = WorkflowAnnotationService(self.session).add(payload, current_user=super_admin)
        self.assertEqual(entity.label, "fail")

    def test_annotation_without_current_user_skips_ownership(self):
        """无 current_user 时跳过归属校验（向后兼容，如系统自动标注）"""
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        payload = {"case_result_id": 1, "label": "pass"}
        entity = WorkflowAnnotationService(self.session).add(payload, current_user=None)
        self.assertEqual(entity.case_result_id, 1)


if __name__ == "__main__":
    unittest.main()
