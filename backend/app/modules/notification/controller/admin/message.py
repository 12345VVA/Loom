"""
通知消息接口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.notification.model.notification import (
    NotificationMessageCreateRequest,
    NotificationMessageRead,
    NotificationMessageSendRequest,
    NotificationRecipientPreviewRequest,
    NotificationMessageUpdateRequest,
)
from app.modules.notification.service.notification_service import NotificationMessageService, NotificationService


@CoolController(
    CoolControllerMeta(
        module="notification",
        resource="message",
        scope="admin",
        service=NotificationMessageService,
        tags=("notification", "message"),
        code_prefix="notification_message",
        list_response_model=NotificationMessageRead,
        page_item_model=NotificationMessageRead,
        info_response_model=NotificationMessageRead,
        add_request_model=NotificationMessageCreateRequest,
        add_response_model=NotificationMessageRead,
        update_request_model=NotificationMessageUpdateRequest,
        update_response_model=NotificationMessageRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("title", "content", "business_key"),
            field_eq=("message_type", "level", "send_status", "source_module"),
            field_like=("title", "content"),
            order_fields=("created_at", "updated_at", "scheduled_at", "expired_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class NotificationMessageController(BaseController):
    @Get("/mine", summary="我的通知", permission="notification:message:mine", role_codes=("admin", "task_operator"))
    async def mine(
        self,
        includeArchived: bool = False,
        messageType: str | None = None,
        readStatus: str | None = None,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).list_for_user(
            current_user.id,
            include_archived=includeArchived,
            message_type=messageType,
            read_status=readStatus,
        )

    @Get("/myInfo", summary="我的通知详情", permission="notification:message:mine", role_codes=("admin", "task_operator"))
    async def my_info(
        self,
        id: int,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).info_for_user(current_user.id, id)

    @Get("/unreadCount", summary="未读数量", permission="notification:message:unreadCount", role_codes=("admin", "task_operator"))
    async def unread_count(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return {"count": NotificationMessageService(session).unread_count(current_user.id)}

    @Post("/read", summary="标记已读", permission="notification:message:read", role_codes=("admin", "task_operator"))
    async def read(
        self,
        payload: dict,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        ids = payload.get("ids") or ([payload.get("id")] if payload.get("id") else [])
        return NotificationMessageService(session).mark_read(current_user.id, ids)

    @Post("/readAll", summary="全部已读", permission="notification:message:readAll", role_codes=("admin", "task_operator"))
    async def read_all(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).mark_all_read(current_user.id)

    @Post("/archive", summary="归档通知", permission="notification:message:archive", role_codes=("admin", "task_operator"))
    async def archive(
        self,
        payload: dict,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        ids = payload.get("ids") or ([payload.get("id")] if payload.get("id") else [])
        return NotificationMessageService(session).archive(current_user.id, ids)

    @Post("/unarchive", summary="取消归档通知", permission="notification:message:unarchive", role_codes=("admin", "task_operator"))
    async def unarchive(
        self,
        payload: dict,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        ids = payload.get("ids") or ([payload.get("id")] if payload.get("id") else [])
        return NotificationMessageService(session).unarchive(current_user.id, ids)

    @Post("/send", summary="发送通知", permission="notification:message:send")
    async def send(
        self,
        payload: NotificationMessageSendRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        message = NotificationService(session).send(
            title=payload.title,
            content=payload.content,
            audience=payload.audience,
            message_type=payload.message_type,
            level=payload.level,
            source_module=payload.source_module,
            business_key=payload.business_key,
            link_url=payload.link_url,
            sender_id=current_user.id,
        )
        return NotificationMessageService(session)._finalize_data(message.model_dump())

    @Post("/previewRecipients", summary="预览通知接收人", permission="notification:message:previewRecipients")
    async def preview_recipients(
        self,
        payload: NotificationRecipientPreviewRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationService(session).preview_recipients(payload.audience)

    @Get("/stats", summary="通知统计", permission="notification:message:stats")
    async def stats(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).stats()

    @Get("/recipients", summary="通知接收人明细", permission="notification:message:recipients")
    async def recipients(
        self,
        id: int,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).recipients(id)

    @Post("/recall", summary="撤回通知", permission="notification:message:recall")
    async def recall(
        self,
        payload: dict,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        message_id = payload.get("id")
        return NotificationMessageService(session).recall(message_id, current_user.id)


router = NotificationMessageController.router
