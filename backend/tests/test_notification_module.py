import os
import sys
import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from fastapi import HTTPException


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.base.model.auth import Department, Role, User, UserRoleLink  # noqa: E402
from app.modules.notification.model.notification import (  # noqa: E402
    AudienceRule,
    NotificationMessage,
    NotificationRecipient,
    NotificationTemplate,
)
from app.modules.notification.service.notification_service import NotificationMessageService, NotificationService  # noqa: E402
from app.modules.task.model.task import TaskInfo, TaskLog  # noqa: E402
from app.modules.task.tasks.system_tasks import _maybe_send_task_notification, _write_task_log  # noqa: E402


class NotificationModuleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Role.__table__,
                Department.__table__,
                UserRoleLink.__table__,
                NotificationMessage.__table__,
                NotificationRecipient.__table__,
                NotificationTemplate.__table__,
                TaskInfo.__table__,
                TaskLog.__table__,
            ],
        )

    def _seed_users(self, session: Session):
        dept = Department(name="研发", parent_id=None)
        child = Department(name="后端", parent_id=1)
        role = Role(name="运营", code="operator", label="运营")
        admin = User(username="admin", full_name="admin", password_hash="x", is_super_admin=True, is_active=True, department_id=1)
        user = User(username="user", full_name="user", password_hash="x", is_active=True, department_id=2)
        session.add_all([dept, child, role, admin, user])
        session.commit()
        session.refresh(role)
        session.refresh(user)
        session.add(UserRoleLink(user_id=user.id, role_id=role.id))
        session.commit()
        return admin, user, role

    def test_send_system_creates_message_and_recipients(self):
        with Session(self.engine) as session:
            admin, _, _ = self._seed_users(session)
            message = NotificationService(session).send_system(title="维护", content="今晚维护")
            recipients = session.exec(select(NotificationRecipient)).all()
            self.assertEqual(message.title, "维护")
            self.assertEqual(len(recipients), 1)
            self.assertEqual(recipients[0].user_id, admin.id)

    def test_resolve_recipients_supports_user_role_department_and_dedup(self):
        with Session(self.engine) as session:
            admin, user, role = self._seed_users(session)
            audience = AudienceRule(users=[user.id], roles=[role.code], departments=[1], all_admins=True)
            users = NotificationService(session).resolve_recipients(audience)
            self.assertEqual({item.id for item in users}, {admin.id, user.id})

    def test_unread_read_and_archive(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="审批",
                content="有新审批",
                audience=AudienceRule(users=[user.id]),
                source_module="workflow",
            )
            service = NotificationMessageService(session)
            self.assertEqual(service.unread_count(user.id), 1)
            service.mark_read(user.id, [message.id])
            self.assertEqual(service.unread_count(user.id), 0)
            service.archive(user.id, [message.id])
            self.assertEqual(service.list_for_user(user.id), [])
            self.assertEqual(len(service.list_for_user(user.id, include_archived=True, read_status="archived")), 1)
            service.unarchive(user.id, [message.id])
            self.assertEqual(len(service.list_for_user(user.id)), 1)

    def test_my_info_blocks_other_users_and_recall_hides_user_side(self):
        with Session(self.engine) as session:
            admin, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="审批",
                content="有新审批",
                audience=AudienceRule(users=[user.id]),
                source_module="workflow",
            )
            service = NotificationMessageService(session)
            with self.assertRaises(HTTPException):
                service.info_for_user(admin.id, message.id)
            self.assertEqual(service.info_for_user(user.id, message.id)["id"], message.id)
            service.recall(message.id, admin.id)
            self.assertEqual(service.list_for_user(user.id), [])

    def test_preview_recipients_matches_send_recipients_and_stats(self):
        with Session(self.engine) as session:
            _, user, role = self._seed_users(session)
            audience = AudienceRule(users=[user.id], roles=[role.code])
            notification = NotificationService(session)
            preview = notification.preview_recipients(audience)
            message = notification.send(
                title="预览",
                content="预览接收人",
                audience=audience,
                message_type="business",
            )
            recipients = session.exec(select(NotificationRecipient).where(NotificationRecipient.message_id == message.id)).all()
            self.assertEqual(preview["count"], len(recipients))
            stats = NotificationMessageService(session).stats()
            self.assertEqual(stats["messageCount"], 1)
            self.assertEqual(stats["recipientCount"], len(recipients))

    def test_template_missing_variable_raises_clear_error(self):
        with Session(self.engine) as session:
            session.add(NotificationTemplate(
                code="task",
                name="任务模板",
                title_template="任务 {taskName}",
                content_template="缺少 {missing}",
            ))
            session.commit()
            with self.assertRaises(HTTPException) as ctx:
                NotificationService(session).render_template("task", {"taskName": "A"})
            self.assertIn("缺少变量", str(ctx.exception.detail))

    def test_template_preview_returns_rendered_payload(self):
        with Session(self.engine) as session:
            session.add(NotificationTemplate(
                code="task",
                name="任务模板",
                title_template="任务 {taskName}",
                content_template="状态 {status}",
                default_level="success",
                default_link_url="/task/info",
            ))
            session.commit()
            result = NotificationService(session).preview_template("task", {"taskName": "A", "status": "成功"})
            self.assertEqual(result["title"], "任务 A")
            self.assertEqual(result["content"], "状态 成功")
            self.assertEqual(result["linkUrl"], "/task/info")

    def test_task_notification_respects_task_config(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            task = TaskInfo(
                id=99,
                name="长任务",
                status=1,
                notify_enabled=True,
                notify_on_success=False,
                notify_on_failure=True,
                notify_on_timeout=True,
                notify_recipients=f'{{"users":[{user.id}]}}',
                notify_timeout_ms=10,
            )
            _maybe_send_task_notification(session, task, 1, "ok", 20)
            messages = session.exec(select(NotificationMessage)).all()
            recipients = session.exec(select(NotificationRecipient)).all()
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].message_type, "task")
            self.assertEqual(recipients[0].user_id, user.id)

    def test_task_log_records_elapsed_milliseconds(self):
        with Session(self.engine) as session:
            log = _write_task_log(session, 99, 0, "任务未配置 service", 7)
            self.assertEqual(log.consume_time, 7)


if __name__ == "__main__":
    unittest.main()
