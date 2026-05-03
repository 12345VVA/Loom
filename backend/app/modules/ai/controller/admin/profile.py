"""
AI 模型调用配置接口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import (
    AiModelProfileCreateRequest,
    AiModelProfileRead,
    AiModelProfileUpdateRequest,
    AiProfileActionRequest,
    AiProfileTestRequest,
)
from app.modules.ai.service.ai_service import AiModelProfileService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="profile",
        scope="admin",
        service=AiModelProfileService,
        tags=("ai", "profile"),
        code_prefix="ai_profile",
        list_response_model=AiModelProfileRead,
        page_item_model=AiModelProfileRead,
        info_response_model=AiModelProfileRead,
        add_request_model=AiModelProfileCreateRequest,
        add_response_model=AiModelProfileRead,
        update_request_model=AiModelProfileUpdateRequest,
        update_response_model=AiModelProfileRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name", "scenario"),
            field_eq=("model_id", "scenario", "is_default", QueryFieldConfig("is_active", "status")),
            field_like=("code", "name", "scenario"),
            order_fields=("created_at", "updated_at", "sort_order", "code"),
            add_order_by=(OrderByConfig("sort_order", "desc"), OrderByConfig("created_at", "desc")),
        ),
        soft_delete=True,
    )
)
class AiModelProfileController(BaseController):
    @Post("/setDefault", summary="设为默认调用配置", permission="ai:profile:setDefault")
    async def set_default(
        self,
        payload: AiProfileActionRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelProfileService(session).set_default(payload.id)

    @Post("/test", summary="测试模型调用配置", permission="ai:profile:test")
    async def test(
        self,
        payload: AiProfileTestRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelProfileService(session).test(payload.id, payload.prompt)


router = AiModelProfileController.router
