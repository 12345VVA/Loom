"""
通知消息接口。
"""

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.notification.model.notification import (
    NotificationIdsRequest,
    NotificationMessageCreateRequest,
    NotificationMessageRead,
    NotificationMessageSendRequest,
    NotificationMessageUpdateRequest,
    NotificationRecipientPreviewRequest,
)
from app.modules.notification.service.notification_service import (
    MAX_IDS_PER_REQUEST,
    MAX_LIST_LIMIT,
    NotificationMessageService,
    NotificationService,
)


def _resolve_ids(payload: NotificationIdsRequest) -> list[int]:
    """归一化单 id / ids 两种形态，并强制数量上限（L7）。"""
    ids = list(payload.ids)
    if not ids and payload.id is not None:
        ids = [payload.id]
    if len(ids) > MAX_IDS_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"单次操作数量不能超过 {MAX_IDS_PER_REQUEST}"
        )
    return ids


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
    def mine(
        self,
        includeArchived: bool = False,
        messageType: str | None = None,
        readStatus: str | None = None,
        limit: int = 0,
        offset: int = 0,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        # 可选分页（F3）：0 表示「不限制」，是默认值，保持既有行为不变（不传即返回全部）。
        # 采用 int = 0 而非 int | None：EPS 生成器
        # （frontend/packages/vite-plugin/src/eps/index.ts:469）取 `p.schema?.type || "string"`，
        # 对 anyOf(number|null) 参数会回退成 `string`，与前端按 number 传参冲突（TS2322）。
        limit = max(0, min(limit, MAX_LIST_LIMIT))
        offset = max(0, offset)
        return NotificationMessageService(session).list_for_user(
            current_user.id,
            include_archived=includeArchived,
            message_type=messageType,
            read_status=readStatus,
            limit=limit or None,
            offset=offset or None,
        )

    @Get(
        "/myInfo", summary="我的通知详情", permission="notification:message:mine", role_codes=("admin", "task_operator")
    )
    def my_info(
        self,
        id: int,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).info_for_user(current_user.id, id)

    @Get(
        "/unreadCount",
        summary="未读数量",
        permission="notification:message:unreadCount",
        role_codes=("admin", "task_operator"),
    )
    def unread_count(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return {"count": NotificationMessageService(session).unread_count(current_user.id)}

    @Post("/read", summary="标记已读", permission="notification:message:read", role_codes=("admin", "task_operator"))
    def read(
        self,
        payload: NotificationIdsRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).mark_read(current_user.id, _resolve_ids(payload))

    @Post(
        "/readAll", summary="全部已读", permission="notification:message:readAll", role_codes=("admin", "task_operator")
    )
    def read_all(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).mark_all_read(current_user.id)

    @Post(
        "/archive", summary="归档通知", permission="notification:message:archive", role_codes=("admin", "task_operator")
    )
    def archive(
        self,
        payload: NotificationIdsRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).archive(current_user.id, _resolve_ids(payload))

    @Post(
        "/unarchive",
        summary="取消归档通知",
        permission="notification:message:unarchive",
        role_codes=("admin", "task_operator"),
    )
    def unarchive(
        self,
        payload: NotificationIdsRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).unarchive(current_user.id, _resolve_ids(payload))

    @Post("/send", summary="发送通知", permission="notification:message:send")
    def send(
        self,
        payload: NotificationMessageSendRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        result = NotificationService(session).send(
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
        data = NotificationMessageService(session)._finalize_data(result.message.model_dump())
        # 回传实际投递人数，供前端确认「到底发给了多少人」（H3）
        data["recipientCount"] = result.recipient_count
        return data

    @Post("/previewRecipients", summary="预览通知接收人", permission="notification:message:previewRecipients")
    def preview_recipients(
        self,
        payload: NotificationRecipientPreviewRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationService(session).preview_recipients(payload.audience)

    @Get("/stats", summary="通知统计", permission="notification:message:stats")
    def stats(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).stats()

    @Get("/recipients", summary="通知接收人明细", permission="notification:message:recipients")
    def recipients(
        self,
        id: int,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationMessageService(session).recipients(id)

    @Post("/recall", summary="撤回通知", permission="notification:message:recall")
    def recall(
        self,
        payload: NotificationIdsRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        message_id = payload.id if payload.id is not None else (payload.ids[0] if payload.ids else None)
        if message_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少通知 id")
        return NotificationMessageService(session).recall(message_id, current_user)


router = NotificationMessageController.router
