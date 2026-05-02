"""
通知模板接口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.notification.model.notification import (
    NotificationTemplateCreateRequest,
    NotificationTemplatePreviewRequest,
    NotificationTemplateRead,
    NotificationTemplateUpdateRequest,
)
from app.modules.notification.service.notification_service import NotificationService, NotificationTemplateService


@CoolController(
    CoolControllerMeta(
        module="notification",
        resource="template",
        scope="admin",
        service=NotificationTemplateService,
        tags=("notification", "template"),
        code_prefix="notification_template",
        list_response_model=NotificationTemplateRead,
        page_item_model=NotificationTemplateRead,
        info_response_model=NotificationTemplateRead,
        add_request_model=NotificationTemplateCreateRequest,
        add_response_model=NotificationTemplateRead,
        update_request_model=NotificationTemplateUpdateRequest,
        update_response_model=NotificationTemplateRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name"),
            field_eq=("is_active", "default_level"),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "code", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class NotificationTemplateController(BaseController):
    @Post("/preview", summary="预览通知模板", permission="notification:template:preview")
    async def preview(
        self,
        payload: NotificationTemplatePreviewRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return NotificationService(session).preview_template(payload.code, payload.context)


router = NotificationTemplateController.router
