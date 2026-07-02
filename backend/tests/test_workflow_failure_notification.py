"""工作流失败节点透传 + 失败通知测试（Task 2 / 5 / 6）。

- Task 2：WorkflowInstanceRead DTO 透传 failed_node_id；SSE failed payload 携带 node_id
- Task 5：workflow.failed 通知模板幂等初始化
- Task 6：_notify_workflow_failure 调用 NotificationService 且异常隔离
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.base.model.auth import User
from app.modules.notification.model.notification import (
    NotificationMessage,
    NotificationRecipient,
    NotificationTemplate,
)
from app.modules.workflow.config import bootstrap as workflow_bootstrap
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowInstanceRead,
)
from app.modules.workflow.tasks.workflow_tasks import (
    _mark_instance_failed,
    _notify_workflow_failure,
)


class WorkflowInstanceReadFailedNodeIdTestCase(unittest.TestCase):
    """Task 2：WorkflowInstanceRead DTO 透传 failed_node_id（camelCase: failedNodeId）。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(
            self.engine,
            tables=[WorkflowDefinition.__table__, WorkflowInstance.__table__],
        )

    def tearDown(self):
        self.engine.dispose()

    def test_dto_contains_failed_node_id(self):
        with Session(self.engine) as session:
            definition = WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1)
            session.add(definition)
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id,
                thread_id="t1",
                status="failed",
                current_node="n2",
                state_data="{}",
                error_message="boom",
                failed_node_id="node_99",
                user_id=1,
            )
            session.add(instance)
            session.commit()
            session.refresh(instance)

            dto = WorkflowInstanceRead.model_validate(instance)
            self.assertEqual(dto.failed_node_id, "node_99")
            # alias 序列化（camelCase）
            dumped = dto.model_dump(by_alias=True)
            self.assertEqual(dumped["failedNodeId"], "node_99")

    def test_dto_failed_node_id_defaults_none(self):
        with Session(self.engine) as session:
            definition = WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1)
            session.add(definition)
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id,
                thread_id="t1",
                status="success",
                state_data="{}",
                user_id=1,
            )
            session.add(instance)
            session.commit()
            session.refresh(instance)

            dto = WorkflowInstanceRead.model_validate(instance)
            self.assertIsNone(dto.failed_node_id)


class WorkflowTemplateBootstrapTestCase(unittest.TestCase):
    """Task 5：workflow.failed 模板幂等初始化。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine, tables=[NotificationTemplate.__table__])

    def tearDown(self):
        self.engine.dispose()

    def test_bootstrap_creates_template(self):
        with Session(self.engine) as session:
            workflow_bootstrap(session)
            tpl = session.exec(
                select(NotificationTemplate).where(NotificationTemplate.code == "workflow.failed")
            ).first()
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.name, "工作流执行失败")
        self.assertEqual(tpl.title_template, "工作流「{workflow_name}」执行失败")
        self.assertEqual(tpl.content_template, "实例 #{instance_id} 在节点 {node_id} 失败：{error_message}")
        self.assertEqual(tpl.default_level, "error")
        self.assertTrue(tpl.is_active)

    def test_bootstrap_idempotent(self):
        """重复调用不报错、不重复插入。"""
        with Session(self.engine) as session:
            workflow_bootstrap(session)
            workflow_bootstrap(session)
            rows = session.exec(
                select(NotificationTemplate).where(NotificationTemplate.code == "workflow.failed")
            ).all()
        self.assertEqual(len(rows), 1)

    def test_template_render_formats_correctly(self):
        """模板用 .format() 渲染，变量用单花括号占位。"""
        with Session(self.engine) as session:
            workflow_bootstrap(session)
            tpl = session.exec(
                select(NotificationTemplate).where(NotificationTemplate.code == "workflow.failed")
            ).first()
        title = tpl.title_template.format(workflow_name="审批流", instance_id=1, node_id="n3", error_message="超时")
        content = tpl.content_template.format(workflow_name="审批流", instance_id=1, node_id="n3", error_message="超时")
        self.assertEqual(title, "工作流「审批流」执行失败")
        self.assertEqual(content, "实例 #1 在节点 n3 失败：超时")


class NotifyWorkflowFailureTestCase(unittest.TestCase):
    """Task 6：_notify_workflow_failure 调用 NotificationService 且异常隔离。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                WorkflowDefinition.__table__,
                WorkflowInstance.__table__,
                NotificationTemplate.__table__,
                NotificationMessage.__table__,
                NotificationRecipient.__table__,
            ],
        )

    def tearDown(self):
        self.engine.dispose()

    def _seed(self, session: Session, failed_node_id: str | None = "node_5") -> WorkflowInstance:
        user = User(username="u1", full_name="u1", password_hash="x", is_active=True)
        definition = WorkflowDefinition(code="wf1", name="测试工作流", is_active=True, user_id=1)
        session.add_all([user, definition])
        session.commit()
        session.refresh(definition)
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id="t1",
            status="failed",
            state_data="{}",
            error_message="节点执行出错",
            failed_node_id=failed_node_id,
            user_id=1,
        )
        session.add(instance)
        session.commit()
        session.refresh(instance)
        workflow_bootstrap(session)
        return instance

    def test_notify_calls_send_business_with_correct_params(self):
        with Session(self.engine) as session:
            instance = self._seed(session)
            instance_id = instance.id

        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch(
                "app.modules.notification.service.notification_service.NotificationService.send_business"
            ) as mock_send,
        ):
            _notify_workflow_failure(instance_id)
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            self.assertEqual(kwargs["source_module"], "workflow")
            self.assertEqual(kwargs["business_key"], str(instance_id))
            self.assertEqual(kwargs["level"], "error")
            self.assertEqual(kwargs["audience"], {"users": [1]})
            self.assertIn("测试工作流", kwargs["title"])
            self.assertIn("node_5", kwargs["content"])
            self.assertIn("节点执行出错", kwargs["content"])

    def test_notify_skips_when_no_user_id(self):
        """实例无 user_id（无接收人）时不发通知。"""
        with Session(self.engine) as session:
            definition = WorkflowDefinition(code="wf1", name="wf", is_active=True, user_id=1)
            session.add(definition)
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id,
                thread_id="t1",
                status="failed",
                state_data="{}",
                user_id=None,
            )
            session.add(instance)
            session.commit()
            instance_id = instance.id

        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch(
                "app.modules.notification.service.notification_service.NotificationService.send_business"
            ) as mock_send,
        ):
            _notify_workflow_failure(instance_id)
            mock_send.assert_not_called()

    def test_notify_exception_does_not_propagate(self):
        """通知异常（如模板渲染失败）仅记 warning，不向上传播。"""
        with Session(self.engine) as session:
            instance = self._seed(session)
            instance_id = instance.id

        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch(
                "app.modules.notification.service.notification_service.NotificationService.render_template",
                side_effect=RuntimeError("template boom"),
            ),
        ):
            _notify_workflow_failure(instance_id)  # 不抛异常即通过

    def test_notify_skips_when_instance_missing(self):
        """实例不存在时静默退出。"""
        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch(
                "app.modules.notification.service.notification_service.NotificationService.send_business"
            ) as mock_send,
        ):
            _notify_workflow_failure(999999)
            mock_send.assert_not_called()


class MarkInstanceFailedPayloadTestCase(unittest.TestCase):
    """Task 2：_mark_instance_failed 的 SSE failed payload 携带 node_id。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                WorkflowDefinition.__table__,
                WorkflowInstance.__table__,
                NotificationTemplate.__table__,
                NotificationMessage.__table__,
                NotificationRecipient.__table__,
            ],
        )

    def tearDown(self):
        self.engine.dispose()

    def _create_running_instance(self) -> int:
        with Session(self.engine) as session:
            user = User(username="u1", full_name="u1", password_hash="x", is_active=True)
            definition = WorkflowDefinition(code="wf1", name="wf", is_active=True, user_id=1)
            session.add_all([user, definition])
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id,
                thread_id="t1",
                status="running",
                state_data="{}",
                user_id=1,
            )
            session.add(instance)
            session.commit()
            return instance.id

    def test_mark_failed_payload_contains_node_id_none_and_notifies(self):
        """_mark_instance_failed（JSON 解析失败等前置错误）payload 的 node_id 为 None，且触发通知。"""
        instance_id = self._create_running_instance()
        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch("app.modules.workflow.tasks.workflow_tasks.publish_event") as mock_pub,
            patch("app.modules.workflow.tasks.workflow_tasks._notify_workflow_failure") as mock_notify,
        ):
            _mark_instance_failed(instance_id, "参数解析失败")
            mock_pub.assert_called_once()
            args = mock_pub.call_args.args
            self.assertEqual(args[1], "failed")
            self.assertEqual(args[2]["status"], "failed")
            self.assertEqual(args[2]["error"], "参数解析失败")
            self.assertEqual(args[2]["node_id"], None)
            mock_notify.assert_called_once_with(instance_id)

        with Session(self.engine) as session:
            refreshed = session.get(WorkflowInstance, instance_id)
            self.assertEqual(refreshed.status, "failed")

    def test_mark_failed_skips_when_status_mismatch(self):
        """实例非 expected 状态时（如已 cancelled）不写终态、不发事件。"""
        instance_id = self._create_running_instance()
        # 先把状态改成 cancelled，_mark_instance_failed(expected="running") 的 CAS 不匹配
        with Session(self.engine) as session:
            inst = session.get(WorkflowInstance, instance_id)
            inst.status = "cancelled"
            session.add(inst)
            session.commit()

        with (
            patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
            patch("app.modules.workflow.tasks.workflow_tasks.publish_event") as mock_pub,
            patch("app.modules.workflow.tasks.workflow_tasks._notify_workflow_failure") as mock_notify,
        ):
            _mark_instance_failed(instance_id, "参数解析失败")
            mock_pub.assert_not_called()
            mock_notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
