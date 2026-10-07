"""
通知模块服务。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from string import Formatter
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlmodel import Session, func, select

from app.core.database import transaction
from app.modules.base.model.auth import Department, Role, User, UserRoleLink
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.notification.model.notification import (
    AudienceRule,
    NotificationMessage,
    NotificationRecipient,
    NotificationRule,
    NotificationTemplate,
)

logger = logging.getLogger(__name__)

SAFE_CONDITIONS = {"active_admins", "super_admins"}

# 客户端在 create / update 中均不得伪造的服务端字段（召回态、发送状态）。
SERVER_OWNED_FIELDS = frozenset({"is_recalled", "recalled_at", "recalled_by", "send_status"})
# 发送者字段：create 时由 current_user 覆盖（无 current_user 的内部调用保留原值以兼容）；
# update 时一律禁止修改（无合法更新路径，避免冒名）。
SENDER_FIELD = "sender_id"

# 单次标记/归档的 id 数量上限，避免超大 IN 列表造成自伤型 DoS（仅控制器入口强制）。
MAX_IDS_PER_REQUEST = 200

# 我的通知列表单次返回条数上限（仅控制器入口钳制）；分页参数 0 表示「不限制」。
MAX_LIST_LIMIT = 200

_PLACEHOLDER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class NotificationSendResult:
    """发送结果：携带消息实体与实际投递收件人数，供调用方判断是否真的发出。"""

    message: NotificationMessage
    recipient_count: int


class NotificationMessageService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, NotificationMessage)
        self._current_user: User | None = None

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """重写 add：接收 current_user 并在 _before_add 中用其覆盖 sender_id，防止客户端伪造。"""
        if isinstance(payload, list):
            return [self.add(item, current_user=current_user) for item in payload]
        self._current_user = current_user
        try:
            return super().add(payload)
        finally:
            self._current_user = None

    def _before_add(self, data: dict) -> dict:
        # 安全修复：剥离服务端独占字段（召回态 / 发送状态）与仅发送用的 audience；
        # 有 current_user 时用其覆盖 sender_id（无 current_user 的内部调用保留原值以兼容）。
        for field in SERVER_OWNED_FIELDS | {"audience"}:
            data.pop(field, None)
        if self._current_user is not None:
            data[SENDER_FIELD] = self._current_user.id
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        """安全修复：更新路径同样剥离服务端独占字段，避免 mass-assignment。

        背景：``update`` 走 ``exclude_unset`` 后对实体逐个 ``setattr``，客户端可借
        `/update` 冒名 ``sender_id``、绕过 ``/recall`` 直接置 ``is_recalled``。
        `audience` 并非实体字段（仅 Create/Send 请求使用），一并剥离以免 setattr 报错。
        """
        for field in SERVER_OWNED_FIELDS | {"audience", SENDER_FIELD}:
            data.pop(field, None)
        return data

    def _after_add(self, entity: NotificationMessage, payload: Any = None) -> None:
        audience = getattr(payload, "audience", None) or AudienceRule(all_admins=True)
        # create_recipients 在 add() 的同一事务内执行；受众为空会抛 400 并回滚，避免孤儿消息。
        NotificationService(self.session).create_recipients(entity, audience)

    def list_for_user(
        self,
        user_id: int,
        include_archived: bool = False,
        message_type: str | None = None,
        read_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        statement = (
            select(NotificationMessage, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.message_id == NotificationMessage.id)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
                # 软删除传导：管理员删除消息后，用户侧不得再看到（H2）
                NotificationMessage.delete_time.is_(None),
            )
            .order_by(NotificationMessage.created_at.desc())
        )
        now = datetime.now(UTC)
        statement = statement.where((NotificationMessage.expired_at.is_(None)) | (NotificationMessage.expired_at > now))
        if message_type:
            statement = statement.where(NotificationMessage.message_type == message_type)
        if read_status == "unread":
            statement = statement.where(NotificationRecipient.is_read == False)  # noqa: E712
        elif read_status == "read":
            statement = statement.where(NotificationRecipient.is_read == True)  # noqa: E712
        # 归档过滤下推 SQL（F3）：与原循环内两处 continue 规则等价——
        #   include_archived=False                       -> 只看未归档
        #   include_archived=True 且 read_status=archived -> 只看已归档
        #   其余                                          -> 不加归档条件
        if not include_archived:
            statement = statement.where(NotificationRecipient.is_archived == False)  # noqa: E712
        elif read_status == "archived":
            statement = statement.where(NotificationRecipient.is_archived == True)  # noqa: E712
        # 可选分页（F3）：默认 None 表示行为完全不变（返回全部），保证向后兼容。
        if offset:
            statement = statement.offset(offset)
        if limit:
            statement = statement.limit(limit)
        rows = self.session.exec(statement).all()
        result: list[dict] = []
        for message, recipient in rows:
            item = self._finalize_data(message.model_dump())
            item["recipientId"] = recipient.id
            item["isRead"] = recipient.is_read
            item["readTime"] = recipient.read_time
            item["isArchived"] = recipient.is_archived
            result.append(item)
        return result

    def unread_count(self, user_id: int) -> int:
        # 口径与 list_for_user 对齐：排除软删除与已过期，避免「徽标常亮、点开为空」（H2/M1）
        # 性能修复（F2）：改为 SQL 标量计数（func.count），不再把全部主键拉回内存再 len()。
        now = datetime.now(UTC)
        conditions = (
            NotificationRecipient.user_id == user_id,
            NotificationRecipient.is_read == False,  # noqa: E712
            NotificationRecipient.is_deleted == False,  # noqa: E712
            NotificationRecipient.is_archived == False,  # noqa: E712
            NotificationMessage.is_recalled == False,  # noqa: E712
            NotificationMessage.delete_time.is_(None),
            (NotificationMessage.expired_at.is_(None)) | (NotificationMessage.expired_at > now),
        )
        statement = (
            select(func.count(NotificationRecipient.id))
            .join(NotificationMessage, NotificationMessage.id == NotificationRecipient.message_id)
            .where(*conditions)
        )
        return self.session.exec(statement).one()

    def info_for_user(self, user_id: int, message_id: int) -> dict:
        row = self.session.exec(
            select(NotificationMessage, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.message_id == NotificationMessage.id)
            .where(
                NotificationMessage.id == message_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
                NotificationMessage.delete_time.is_(None),
            )
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
        message, recipient = row
        if message.expired_at and message.expired_at <= datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知已过期")
        item = self._finalize_data(message.model_dump())
        item["recipientId"] = recipient.id
        item["isRead"] = recipient.is_read
        item["readTime"] = recipient.read_time
        item["isArchived"] = recipient.is_archived
        return item

    def mark_read(self, user_id: int, ids: list[int]) -> dict:
        if not ids:
            return {"success": True, "count": 0}
        now = datetime.now(UTC)
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
        # 只处理有效消息（未召回、未软删），不再顺带把已召回通知置为已读（L6）
        ids = [
            row.message_id
            for row in self.session.exec(
                select(NotificationRecipient)
                .join(NotificationMessage, NotificationMessage.id == NotificationRecipient.message_id)
                .where(
                    NotificationRecipient.user_id == user_id,
                    NotificationRecipient.is_read == False,  # noqa: E712
                    NotificationRecipient.is_deleted == False,  # noqa: E712
                    NotificationMessage.is_recalled == False,  # noqa: E712
                    NotificationMessage.delete_time.is_(None),
                )
            ).all()
        ]
        return self.mark_read(user_id, ids)

    def archive(self, user_id: int, ids: list[int]) -> dict:
        if not ids:
            return {"success": True, "count": 0}
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
        if not ids:
            return {"success": True, "count": 0}
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
        # 统一口径：分子/分母同源（排除软删除消息、已召回消息、已删除收件人），避免已读率失真（L2）
        valid_message_ids = select(NotificationMessage.id).where(
            NotificationMessage.delete_time.is_(None),
            NotificationMessage.is_recalled == False,  # noqa: E712
        )
        effective_recipient = (
            NotificationRecipient.is_deleted == False,  # noqa: E712
            NotificationRecipient.message_id.in_(valid_message_ids),
        )
        total_messages = self.session.exec(
            select(func.count(NotificationMessage.id)).where(NotificationMessage.delete_time.is_(None))
        ).one()
        total_recipients = self.session.exec(
            select(func.count(NotificationRecipient.id)).where(*effective_recipient)
        ).one()
        read_count = self.session.exec(
            select(func.count(NotificationRecipient.id)).where(
                *effective_recipient, NotificationRecipient.is_read.is_(True)
            )
        ).one()
        unread_count = self.session.exec(
            select(func.count(NotificationRecipient.id)).where(
                *effective_recipient, NotificationRecipient.is_read.is_(False)
            )
        ).one()
        recalled_count = self.session.exec(
            select(func.count(NotificationMessage.id)).where(
                NotificationMessage.is_recalled == True,  # noqa: E712
                NotificationMessage.delete_time.is_(None),
            )
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
                # 与全站时间字段命名对齐（created_at -> createTime），避免同一模块两种命名（N2）
                "createTime": recipient.created_at,
            }
            for recipient, user in rows
        ]

    def recall(self, message_id: int, operator: User) -> dict:
        message = self.session.get(NotificationMessage, message_id)
        if not message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
        # 归属校验：仅发送者本人或超级管理员可撤回，避免任意持权者撤回他人通知且不可逆（M6）
        if not getattr(operator, "is_super_admin", False) and message.sender_id != operator.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅发送者或超级管理员可撤回该通知")
        with transaction(self.session):
            message.is_recalled = True
            message.recalled_at = datetime.now(UTC)
            message.recalled_by = operator.id
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
        message, _ = self._send(
            title=title,
            content=content,
            audience=audience or AudienceRule(all_admins=True),
            message_type="system",
            level=level,
            source_module="system",
            link_url=link_url,
        )
        return message

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
        message, _ = self._send(
            title=title,
            content=content,
            audience=audience,
            message_type="business",
            level=level,
            source_module=source_module,
            business_key=business_key,
            link_url=link_url,
        )
        return message

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
            "executedAt": datetime.now(UTC).isoformat(),
        }
        if template_code:
            title, content, level, link_url = self.render_template(template_code, context)
        else:
            kind = "超时" if timeout else context["status"]
            title = f"任务{kind}: {task_name}"
            content = f"任务 {task_name} 执行{kind}，耗时 {consume_time}ms。{detail or ''}"
            level = "warning" if timeout else ("success" if status_value == 1 else "error")
            link_url = None
        message, _ = self._send(
            title=title,
            content=content,
            audience=audience,
            message_type="task",
            level=level,
            source_module="task",
            business_key=str(task_id),
            link_url=link_url,
        )
        return message

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
    ) -> NotificationSendResult:
        """发送通知并返回投递结果（含实际收件人数），供控制器回传前端（H3）。"""
        message, recipients = self._send(
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
        return NotificationSendResult(message=message, recipient_count=len(recipients))

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
            select(NotificationTemplate).where(
                NotificationTemplate.code == code,
                NotificationTemplate.is_active == True,  # noqa: E712
            )
        ).first()
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知模板不存在或已禁用")
        missing = _missing_template_keys(template.title_template, context) | _missing_template_keys(
            template.content_template, context
        )
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"通知模板缺少变量: {', '.join(sorted(missing))}"
            )
        try:
            title = template.title_template.format(**context)
            content = template.content_template.format(**context)
        except (KeyError, IndexError, ValueError, AttributeError) as exc:
            # 兜底：即便校验放行，渲染异常也应收敛为 400，而非 500（M5）
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"通知模板渲染失败: {exc}") from exc
        return title, content, template.default_level, template.default_link_url

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
                    for row in self.session.exec(
                        select(UserRoleLink).where(UserRoleLink.role_id.in_(resolved_role_ids))
                    ).all()
                ]
                if user_ids:
                    statements.append(select(User).where(User.id.in_(user_ids), User.is_active == True))  # noqa: E712

        department_ids = set(audience.departments)
        if audience.include_child_departments and department_ids:
            department_ids.update(self._collect_child_departments(department_ids))
        if department_ids:
            statements.append(select(User).where(User.department_id.in_(department_ids), User.is_active == True))  # noqa: E712

        if audience.condition in ("active_admins", "super_admins"):
            # F4：super_admins 原先漏过滤停用账号，导致「已停用超管仍收到通知」；
            # 两条分支统一要求 is_active，语义一致（停用账号不再投递）。
            statements.append(select(User).where(User.is_active == True, User.is_super_admin == True))  # noqa: E712

        users: dict[int, User] = {}
        for statement in statements:
            for user in self.session.exec(statement).all():
                if user.id is not None:
                    users[user.id] = user
        return list(users.values())

    def create_recipients(
        self, message: NotificationMessage, audience: AudienceRule | dict | str | None
    ) -> list[NotificationRecipient]:
        """解析受众并写入收件人。

        调用方负责事务边界：`_send` 与 `add()` 均已在同一事务内调用本方法，因此这里**不**
        自行开事务——消息与收件人必须原子落库，避免产生「0 收件人的孤儿消息」（H1）。
        受众解析为空时抛 400，由外层事务回滚消息本身（H3）。
        """
        users = self.resolve_recipients(audience)
        if not users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知受众未匹配到任何有效接收人")
        return self._insert_recipients(message, users)

    def _insert_recipients(self, message: NotificationMessage, users: list[User]) -> list[NotificationRecipient]:
        # 性能修复（F1）：原按用户逐个 select 查重，N 个收件人触发 2N 次 SQL；
        # 改为一次性 IN 查询已存在的 user_id 集合，仅插入差集并用 add_all 批量落库。
        # 语义不变：仍返回「本次实际插入的 recipient 列表」。
        if message.id is None:
            return []
        candidate_ids = [user.id for user in users if user.id is not None]
        if not candidate_ids:
            return []
        existing_ids = set(
            self.session.exec(
                select(NotificationRecipient.user_id).where(
                    NotificationRecipient.message_id == message.id,
                    NotificationRecipient.user_id.in_(candidate_ids),
                )
            ).all()
        )
        rows = [
            NotificationRecipient(message_id=message.id, user_id=user.id, department_id=user.department_id)
            for user in users
            if user.id is not None and user.id not in existing_ids
        ]
        if rows:
            self.session.add_all(rows)
        return rows

    def _send(self, **kwargs: Any) -> tuple[NotificationMessage, list[NotificationRecipient]]:
        """单事务投递：消息与收件人原子落库（H1）。

        先解析受众（只读，为空或非法即中止、不产生任何写入），再在同一事务内插入消息并
        flush 取 id，最后写入收件人；任一步异常整体回滚，杜绝孤儿消息。
        """
        audience = kwargs.pop("audience")
        users = self.resolve_recipients(audience)
        if not users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知受众未匹配到任何有效接收人")
        message = NotificationMessage(**kwargs)
        with transaction(self.session):
            self.session.add(message)
            self.session.flush()
            recipients = self._insert_recipients(message, users)
        self.session.refresh(message)
        return message, recipients

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
        if not rule.strip():
            return AudienceRule()
        try:
            data = json.loads(rule)
        except (json.JSONDecodeError, ValueError) as exc:
            # 畸形受众 JSON 收敛为 400，避免脏数据（如 TaskInfo.notify_recipients）直达 Celery 抛 500（M4）
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知受众 JSON 格式非法") from exc
    else:
        data = rule
    try:
        return AudienceRule.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知受众字段非法") from exc


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
    """校验模板占位符并返回缺失变量集合。

    收紧原因（M5）：旧的 ``if field_name`` 过滤会放行自动编号 ``{}``（field_name 为空串）
    与嵌套格式说明符 ``{a:{w}}``，二者在 ``str.format`` 阶段分别抛 IndexError / KeyError 造成 500。
    此处仅允许「简单变量名」占位符，其余一律 400。
    """
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"通知模板语法错误: {exc}") from exc

    keys: set[str] = set()
    for _, field_name, format_spec, _ in parsed:
        if field_name is None:
            continue
        if field_name == "":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知模板不支持自动编号占位符 {}")
        if format_spec:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通知模板不支持嵌套格式说明符")
        if not _PLACEHOLDER_RE.fullmatch(field_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"通知模板占位符仅支持简单变量名: {field_name}"
            )
        keys.add(field_name)
    return {key for key in keys if key not in context}
