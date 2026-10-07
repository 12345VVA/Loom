import os
import sys
import unittest
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from helpers import make_test_engine  # noqa: E402

from app.modules.base.model.auth import Department, Role, User, UserRoleLink  # noqa: E402
from app.modules.base.model.sys import SysLog, SysLoginLog  # noqa: E402
from app.modules.notification.model.notification import (  # noqa: E402
    AudienceRule,
    NotificationMessage,
    NotificationMessageUpdateRequest,
    NotificationRecipient,
    NotificationTemplate,
)
from app.modules.notification.service.notification_service import (  # noqa: E402
    NotificationMessageService,
    NotificationService,
)
from app.modules.task.model.task import TaskInfo, TaskLog  # noqa: E402
from app.modules.task.tasks.system_tasks import _maybe_send_task_notification, _write_task_log  # noqa: E402


class NotificationModuleTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
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
                SysLog.__table__,
                SysLoginLog.__table__,
            ],
        )

    def _seed_users(self, session: Session):
        dept = Department(name="研发", parent_id=None)
        child = Department(name="后端", parent_id=1)
        role = Role(name="运营", code="operator", label="运营")
        admin = User(
            username="admin", full_name="admin", password_hash="x", is_super_admin=True, is_active=True, department_id=1
        )
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
            service.recall(message.id, admin)
            self.assertEqual(service.list_for_user(user.id), [])

    def test_preview_recipients_matches_send_recipients_and_stats(self):
        with Session(self.engine) as session:
            _, user, role = self._seed_users(session)
            audience = AudienceRule(users=[user.id], roles=[role.code])
            notification = NotificationService(session)
            preview = notification.preview_recipients(audience)
            result = notification.send(
                title="预览",
                content="预览接收人",
                audience=audience,
                message_type="business",
            )
            message = result.message
            self.assertEqual(result.recipient_count, preview["count"])
            recipients = session.exec(
                select(NotificationRecipient).where(NotificationRecipient.message_id == message.id)
            ).all()
            self.assertEqual(preview["count"], len(recipients))
            stats = NotificationMessageService(session).stats()
            self.assertEqual(stats["messageCount"], 1)
            self.assertEqual(stats["recipientCount"], len(recipients))

    def test_template_missing_variable_raises_clear_error(self):
        with Session(self.engine) as session:
            session.add(
                NotificationTemplate(
                    code="task",
                    name="任务模板",
                    title_template="任务 {taskName}",
                    content_template="缺少 {missing}",
                )
            )
            session.commit()
            with self.assertRaises(HTTPException) as ctx:
                NotificationService(session).render_template("task", {"taskName": "A"})
            self.assertIn("缺少变量", str(ctx.exception.detail))

    def test_template_preview_returns_rendered_payload(self):
        with Session(self.engine) as session:
            session.add(
                NotificationTemplate(
                    code="task",
                    name="任务模板",
                    title_template="任务 {taskName}",
                    content_template="状态 {status}",
                    default_level="success",
                    default_link_url="/task/info",
                )
            )
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

    # ---- H3：空受众拒绝，且不留下孤儿消息 ----
    def test_send_rejects_empty_audience_without_orphan(self):
        with Session(self.engine) as session:
            self._seed_users(session)
            with self.assertRaises(HTTPException) as ctx:
                NotificationService(session).send(
                    title="空受众",
                    content="x",
                    audience=AudienceRule(),
                    message_type="business",
                )
            self.assertEqual(ctx.exception.status_code, 400)
            session.rollback()
            self.assertEqual(session.exec(select(NotificationMessage)).all(), [])

    # ---- H1/M4：畸形受众 JSON 收敛为 400 且整体回滚 ----
    def test_send_rollback_on_malformed_audience(self):
        with Session(self.engine) as session:
            self._seed_users(session)
            with self.assertRaises(HTTPException) as ctx:
                NotificationService(session).send_business(
                    title="畸形受众",
                    content="x",
                    audience="{bad",
                    source_module="test",
                )
            self.assertEqual(ctx.exception.status_code, 400)
            session.rollback()
            self.assertEqual(session.exec(select(NotificationMessage)).all(), [])

    # ---- H2：消息软删除不向用户侧传导 ----
    def test_soft_deleted_message_hidden_from_user(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="将删除", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            service = NotificationMessageService(session)
            self.assertEqual(service.unread_count(user.id), 1)
            message.delete_time = datetime.now(UTC)
            session.add(message)
            session.commit()
            self.assertEqual(service.list_for_user(user.id), [])
            self.assertEqual(service.unread_count(user.id), 0)
            with self.assertRaises(HTTPException):
                service.info_for_user(user.id, message.id)

    # ---- M1：未读数与列表同样排除已过期 ----
    def test_unread_count_excludes_expired(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="过期", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            service = NotificationMessageService(session)
            self.assertEqual(service.unread_count(user.id), 1)
            message.expired_at = datetime.now(UTC) - timedelta(hours=1)
            session.add(message)
            session.commit()
            self.assertEqual(service.unread_count(user.id), 0)
            self.assertEqual(service.list_for_user(user.id), [])

    # ---- M2：更新路径不得伪造服务端字段 ----
    def test_update_cannot_forge_server_fields(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="原始", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            NotificationMessageService(session).update(
                {"id": message.id, "sender_id": 999, "is_recalled": True, "send_status": "pending", "title": "改标题"}
            )
            session.refresh(message)
            self.assertEqual(message.sender_id, None)
            self.assertFalse(message.is_recalled)
            self.assertEqual(message.send_status, "sent")
            self.assertEqual(message.title, "改标题")

    # ---- M2：携带 audience 的更新不再 500 ----
    def test_update_with_audience_does_not_500(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            message = NotificationService(session).send_business(
                title="原始", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            payload = NotificationMessageUpdateRequest.model_validate(
                {"id": message.id, "title": "新标题", "audience": {"users": [user.id]}}
            )
            NotificationMessageService(session).update(payload)
            session.refresh(message)
            self.assertEqual(message.title, "新标题")

    # ---- M6：撤回需发送者本人或超管 ----
    def test_recall_requires_sender_ownership(self):
        with Session(self.engine) as session:
            admin, user, _ = self._seed_users(session)
            # sender_id 设为普通 user 的 id
            message = (
                NotificationService(session)
                .send(
                    title="他人消息",
                    content="x",
                    audience=AudienceRule(users=[user.id]),
                    message_type="business",
                    sender_id=user.id,
                )
                .message
            )
            other = User(username="other", full_name="other", password_hash="x", is_active=True)
            session.add(other)
            session.commit()
            session.refresh(other)
            service = NotificationMessageService(session)
            with self.assertRaises(HTTPException) as ctx:
                service.recall(message.id, other)
            self.assertEqual(ctx.exception.status_code, 403)
            # 超管可撤回
            self.assertTrue(service.recall(message.id, admin)["success"])

    # ---- M5：模板自动编号 / 嵌套 spec / 非法名一律拒绝 ----
    def test_template_rejects_auto_numbering_and_nested_spec(self):
        with Session(self.engine) as session:
            session.add(NotificationTemplate(code="bad1", name="自动编号", title_template="{}", content_template="x"))
            session.add(NotificationTemplate(code="bad2", name="嵌套", title_template="{a:{w}}", content_template="x"))
            session.commit()
            service = NotificationService(session)
            with self.assertRaises(HTTPException) as ctx1:
                service.render_template("bad1", {"a": 1})
            self.assertEqual(ctx1.exception.status_code, 400)
            with self.assertRaises(HTTPException) as ctx2:
                service.render_template("bad2", {"a": 1, "w": 2})
            self.assertEqual(ctx2.exception.status_code, 400)

    # ---- L6：全部已读不覆盖已召回 ----
    def test_mark_all_read_excludes_recalled(self):
        with Session(self.engine) as session:
            admin, user, _ = self._seed_users(session)
            notification = NotificationService(session)
            keep = notification.send_business(
                title="保留", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            recalled = notification.send_business(
                title="撤回", content="x", audience=AudienceRule(users=[user.id]), source_module="test"
            )
            service = NotificationMessageService(session)
            service.recall(recalled.id, admin)
            service.mark_all_read(user.id)
            keep_row = session.exec(
                select(NotificationRecipient).where(NotificationRecipient.message_id == keep.id)
            ).first()
            recalled_row = session.exec(
                select(NotificationRecipient).where(NotificationRecipient.message_id == recalled.id)
            ).first()
            self.assertTrue(keep_row.is_read)
            self.assertFalse(recalled_row.is_read)

    # ---- M3：任务通知失败不得抛出（不污染任务终态） ----
    def test_task_notification_failure_does_not_raise(self):
        with Session(self.engine) as session:
            _, user, _ = self._seed_users(session)
            task = TaskInfo(
                id=100,
                name="坏模板任务",
                status=0,
                notify_enabled=True,
                notify_on_failure=True,
                notify_recipients=f'{{"users":[{user.id}]}}',
                notify_template_code="missing.template",
            )
            # 不应抛出异常
            _maybe_send_task_notification(session, task, 0, "boom", 5)
            self.assertEqual(session.exec(select(NotificationMessage)).all(), [])


if __name__ == "__main__":
    unittest.main()
