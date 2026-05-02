"""
通知模块服务。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from string import Formatter
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, func, select

from app.core.database import transaction
from app.modules.base.model.auth import Department, Role, User, UserRoleLink
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.notification.model.notification import (
    AudienceRule,
    NotificationMessage,
    NotificationMessageCreateRequest,
    NotificationRecipient,
    NotificationRule,
    NotificationTemplate,
)

SAFE_CONDITIONS = {"active_admins", "super_admins"}


class NotificationMessageService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, NotificationMessage)

    def _after_add(self, entity: NotificationMessage, payload: Any = None) -> None:
        audience = getattr(payload, "audience", None) or AudienceRule(all_admins=True)
        NotificationService(self.session).create_recipients(entity, audience)

    def list_for_user(
        self,
        user_id: int,
        include_archived: bool = False,
        message_type: str | None = None,
        read_status: str | None = None,
    ) -> list[dict]:
        statement = (
            select(NotificationMessage, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.message_id == NotificationMessage.id)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
            )
            .order_by(NotificationMessage.created_at.desc())
        )
        now = datetime.utcnow()
        statement = statement.where((NotificationMessage.expired_at.is_(None)) | (NotificationMessage.expired_at > now))
        if message_type:
            statement = statement.where(NotificationMessage.message_type == message_type)
        if read_status == "unread":
            statement = statement.where(NotificationRecipient.is_read == False)  # noqa: E712
        elif read_status == "read":
            statement = statement.where(NotificationRecipient.is_read == True)  # noqa: E712
        rows = self.session.exec(statement).all()
        result: list[dict] = []
        for message, recipient in rows:
            if recipient.is_archived and not include_archived:
                continue
            if include_archived and read_status == "archived" and not recipient.is_archived:
                continue
            item = self._finalize_data(message.model_dump())
            item["recipientId"] = recipient.id
            item["isRead"] = recipient.is_read
            item["readTime"] = recipient.read_time
            item["isArchived"] = recipient.is_archived
            result.append(item)
        return result

    def unread_count(self, user_id: int) -> int:
        return len(self.session.exec(
            select(NotificationRecipient.id).where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_read == False,  # noqa: E712
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationRecipient.is_archived == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
            )
            .join(NotificationMessage, NotificationMessage.id == NotificationRecipient.message_id)
        ).all())

    def info_for_user(self, user_id: int, message_id: int) -> dict:
        row = self.session.exec(
            select(NotificationMessage, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.message_id == NotificationMessage.id)
            .where(
                NotificationMessage.id == message_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
            )
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
        message, recipient = row
        if message.expired_at and message.expired_at <= datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知已过期")
        item = self._finalize_data(message.model_dump())
        item["recipientId"] = recipient.id
        item["isRead"] = recipient.is_read
        item["readTime"] = recipient.read_time
        item["isArchived"] = recipient.is_archived
        return item

    def mark_read(self, user_id: int, ids: list[int]) -> dict:
        now = datetime.utcnow()
        rows = self.session.exec(
            select(NotificationRecipient).where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.message_id.in_(ids),
                NotificationRecipient.is_deleted == False,  # noqa: E712
            )
        ).all()
        with transaction(self.session):
            for row in rows:
                row.is_read = True
                row.read_time = row.read_time or now
                self.session.add(row)
        return {"success": True, "count": len(rows)}

    def mark_all_read(self, user_id: int) -> dict:
        ids = [
            row.message_id
            for row in self.session.exec(
                select(NotificationRecipient).where(
                    NotificationRecipient.user_id == user_id,
                    NotificationRecipient.is_read == False,  # noqa: E712
                    NotificationRecipient.is_deleted == False,  # noqa: E712
                )
            ).all()
        ]
        return self.mark_read(user_id, ids)

    def archive(self, user_id: int, ids: list[int]) -> dict:
        rows = self.session.exec(
            select(NotificationRecipient).where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.message_id.in_(ids),
                NotificationRecipient.is_deleted == False,  # noqa: E712
            )
        ).all()
        with transaction(self.session):
            for row in rows:
                row.is_archived = True
                self.session.add(row)
        return {"success": True, "count": len(rows)}

    def unarchive(self, user_id: int, ids: list[int]) -> dict:
        rows = self.session.exec(
            select(NotificationRecipient).where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.message_id.in_(ids),
                NotificationRecipient.is_deleted == False,  # noqa: E712
            )
        ).all()
        with transaction(self.session):
            for row in rows:
                row.is_archived = False
                self.session.add(row)
        return {"success": True, "count": len(rows)}

    def stats(self) -> dict:
        total_messages = self.session.exec(select(func.count(NotificationMessage.id))).one()
        total_recipients = self.session.exec(select(func.count(NotificationRecipient.id))).one()
        read_count = self.session.exec(
            select(func.count(NotificationRecipient.id)).where(NotificationRecipient.is_read == True)  # noqa: E712
        ).one()
        unread_count = self.session.exec(
            select(func.count(NotificationRecipient.id)).where(
                NotificationRecipient.is_read == False,  # noqa: E712
                NotificationRecipient.is_deleted == False,  # noqa: E712
            )
        ).one()
        recalled_count = self.session.exec(
            select(func.count(NotificationMessage.id)).where(NotificationMessage.is_recalled == True)  # noqa: E712
        ).one()
        return {
            "messageCount": total_messages,
            "recipientCount": total_recipients,
            "readCount": read_count,
            "unreadCount": unread_count,
            "recalledCount": recalled_count,
            "readRate": round((read_count / total_recipients * 100) if total_recipients else 0, 2),
        }

    def recipients(self, message_id: int) -> list[dict]:
        rows = self.session.exec(
            select(NotificationRecipient, User)
            .join(User, User.id == NotificationRecipient.user_id)
            .where(NotificationRecipient.message_id == message_id)
            .order_by(NotificationRecipient.created_at.desc())
        ).all()
        return [
            {
                "id": recipient.id,
                "messageId": recipient.message_id,
                "userId": user.id,
                "username": user.username,
                "name": user.full_name,
                "isRead": recipient.is_read,
                "readTime": recipient.read_time,
                "isArchived": recipient.is_archived,
                "isDeleted": recipient.is_deleted,
                "createdAt": recipient.created_at,
            }
            for recipient, user in rows
        ]

    def recall(self, message_id: int, operator_id: int) -> dict:
        message = self.session.get(NotificationMessage, message_id)
        if not message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
        with transaction(self.session):
            message.is_recalled = True
            message.recalled_at = datetime.utcnow()
            message.recalled_by = operator_id
            self.session.add(message)
        return {"success": True}


class NotificationTemplateService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, NotificationTemplate)

    def _before_add(self, data: dict) -> dict:
        self._ensure_unique_code(data.get("code"))
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        return data

    def _ensure_unique_code(self, code: str | None, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(NotificationTemplate).where(NotificationTemplate.code == code)
        if exclude_id is not None:
            statement = statement.where(NotificationTemplate.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模板编码已存在")


class NotificationRuleService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, NotificationRule)

    def _before_add(self, data: dict) -> dict:
        self._validate_condition(data.get("condition"))
        self._ensure_unique_code(data.get("code"))
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        self._validate_condition(data.get("condition"))
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        return data

    def _ensure_unique_code(self, code: str | None, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(NotificationRule).where(NotificationRule.code == code)
        if exclude_id is not None:
            statement = statement.where(NotificationRule.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="规则编码已存在")

    def _validate_condition(self, condition: str | None) -> None:
        if condition and condition not in SAFE_CONDITIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的通知条件")


class NotificationService:
    def __init__(self, session: Session):
        self.session = session

    def send_system(
        self,
        *,
        title: str,
        content: str,
        audience: AudienceRule | dict | None = None,
        level: str = "info",
        link_url: str | None = None,
    ) -> NotificationMessage:
        return self._send(
            title=title,
            content=content,
            audience=audience or AudienceRule(all_admins=True),
            message_type="system",
            level=level,
            source_module="system",
            link_url=link_url,
        )

    def send_business(
        self,
        *,
        title: str,
        content: str,
        audience: AudienceRule | dict,
        source_module: str,
        business_key: str | None = None,
        level: str = "info",
        link_url: str | None = None,
    ) -> NotificationMessage:
        return self._send(
            title=title,
            content=content,
            audience=audience,
            message_type="business",
            level=level,
            source_module=source_module,
            business_key=business_key,
            link_url=link_url,
        )

    def send_task(
        self,
        *,
        task_name: str,
        task_id: int,
        status_value: int,
        consume_time: int,
        detail: str | None,
        audience: AudienceRule | dict,
        template_code: str | None = None,
        timeout: bool = False,
    ) -> NotificationMessage:
        context = {
            "taskName": task_name,
            "taskId": task_id,
            "status": "成功" if status_value == 1 else "失败",
            "consumeTime": consume_time,
            "detail": detail or "",
            "executedAt": datetime.utcnow().isoformat(),
        }
        if template_code:
            title, content, level, link_url = self.render_template(template_code, context)
        else:
            kind = "超时" if timeout else context["status"]
            title = f"任务{kind}: {task_name}"
            content = f"任务 {task_name} 执行{kind}，耗时 {consume_time}ms。{detail or ''}"
            level = "warning" if timeout else ("success" if status_value == 1 else "error")
            link_url = None
        return self._send(
            title=title,
            content=content,
            audience=audience,
            message_type="task",
            level=level,
            source_module="task",
            business_key=str(task_id),
            link_url=link_url,
        )

    def send(
        self,
        *,
        title: str,
        content: str,
        audience: AudienceRule | dict,
        message_type: str = "business",
        level: str = "info",
        source_module: str | None = None,
        business_key: str | None = None,
        link_url: str | None = None,
        sender_id: int | None = None,
    ) -> NotificationMessage:
        return self._send(
            title=title,
            content=content,
            audience=audience,
            message_type=message_type,
            level=level,
            source_module=source_module,
            business_key=business_key,
            link_url=link_url,
            sender_id=sender_id,
        )

    def preview_recipients(self, audience: AudienceRule | dict | str | None) -> dict:
        users = self.resolve_recipients(audience)
        sample = [
            {
                "id": user.id,
                "username": user.username,
                "name": user.full_name,
                "departmentId": user.department_id,
            }
            for user in users[:20]
        ]
        return {"count": len(users), "sample": sample}

    def render_template(self, code: str, context: dict[str, Any]) -> tuple[str, str, str, str | None]:
        template = self.session.exec(
            select(NotificationTemplate).where(NotificationTemplate.code == code, NotificationTemplate.is_active == True)  # noqa: E712
        ).first()
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知模板不存在或已禁用")
        missing = _missing_template_keys(template.title_template, context) | _missing_template_keys(template.content_template, context)
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"通知模板缺少变量: {', '.join(sorted(missing))}")
        return (
            template.title_template.format(**context),
            template.content_template.format(**context),
            template.default_level,
            template.default_link_url,
        )

    def preview_template(self, code: str, context: dict[str, Any]) -> dict:
        title, content, level, link_url = self.render_template(code, context)
        return {
            "title": title,
            "content": content,
            "level": level,
            "linkUrl": link_url,
        }

    def resolve_recipients(self, rule: AudienceRule | dict | str | None) -> list[User]:
        audience = _normalize_audience(rule)
        if audience.condition and audience.condition not in SAFE_CONDITIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的通知条件")

        statements = []
        if audience.all_admins:
            statements.append(select(User).where(User.is_active == True, User.is_super_admin == True))  # noqa: E712

        if audience.users:
            statements.append(select(User).where(User.id.in_(audience.users), User.is_active == True))  # noqa: E712

        role_ids, role_codes = _split_role_refs(audience.roles)
        if role_ids or role_codes:
            role_statement = select(Role.id)
            clauses = []
            if role_ids:
                clauses.append(Role.id.in_(role_ids))
            if role_codes:
                clauses.append(Role.code.in_(role_codes))
            if len(clauses) == 1:
                role_statement = role_statement.where(clauses[0])
            elif clauses:
                from sqlalchemy import or_
                role_statement = role_statement.where(or_(*clauses))
            resolved_role_ids = [row for row in self.session.exec(role_statement).all() if row is not None]
            if resolved_role_ids:
                user_ids = [
                    row.user_id
                    for row in self.session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(resolved_role_ids))).all()
                ]
                if user_ids:
                    statements.append(select(User).where(User.id.in_(user_ids), User.is_active == True))  # noqa: E712

        department_ids = set(audience.departments)
        if audience.include_child_departments and department_ids:
            department_ids.update(self._collect_child_departments(department_ids))
        if department_ids:
            statements.append(select(User).where(User.department_id.in_(department_ids), User.is_active == True))  # noqa: E712

        if audience.condition == "active_admins":
            statements.append(select(User).where(User.is_active == True, User.is_super_admin == True))  # noqa: E712
        elif audience.condition == "super_admins":
            statements.append(select(User).where(User.is_super_admin == True))  # noqa: E712

        users: dict[int, User] = {}
        for statement in statements:
            for user in self.session.exec(statement).all():
                if user.id is not None:
                    users[user.id] = user
        return list(users.values())

    def create_recipients(self, message: NotificationMessage, audience: AudienceRule | dict | str | None) -> list[NotificationRecipient]:
        users = self.resolve_recipients(audience)
        recipients: list[NotificationRecipient] = []
        with transaction(self.session):
            for user in users:
                if message.id is None or user.id is None:
                    continue
                exists = self.session.exec(
                    select(NotificationRecipient).where(
                        NotificationRecipient.message_id == message.id,
                        NotificationRecipient.user_id == user.id,
                    )
                ).first()
                if exists:
                    continue
                row = NotificationRecipient(
                    message_id=message.id,
                    user_id=user.id,
                    department_id=user.department_id,
                )
                self.session.add(row)
                recipients.append(row)
        return recipients

    def _send(self, **kwargs: Any) -> NotificationMessage:
        audience = kwargs.pop("audience")
        message = NotificationMessage(**kwargs)
        with transaction(self.session):
            self.session.add(message)
        self.session.refresh(message)
        self.create_recipients(message, audience)
        return message

    def _collect_child_departments(self, department_ids: set[int]) -> set[int]:
        children: set[int] = set()
        pending = set(department_ids)
        while pending:
            rows = self.session.exec(select(Department).where(Department.parent_id.in_(pending))).all()
            pending = {row.id for row in rows if row.id is not None and row.id not in children}
            children.update(pending)
        return children


def _normalize_audience(rule: AudienceRule | dict | str | None) -> AudienceRule:
    if rule is None:
        return AudienceRule()
    if isinstance(rule, AudienceRule):
        return rule
    if isinstance(rule, str):
        data = json.loads(rule) if rule.strip() else {}
        return AudienceRule.model_validate(data)
    return AudienceRule.model_validate(rule)


def _split_role_refs(values: list[int | str]) -> tuple[list[int], list[str]]:
    role_ids: list[int] = []
    role_codes: list[str] = []
    for value in values:
        if isinstance(value, int):
            role_ids.append(value)
            continue
        if isinstance(value, str) and re.fullmatch(r"\d+", value):
            role_ids.append(int(value))
        elif isinstance(value, str) and value:
            role_codes.append(value)
    return role_ids, role_codes


def _missing_template_keys(template: str, context: dict[str, Any]) -> set[str]:
    keys = {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}
    return {key for key in keys if key not in context}
