"""
AI 厂商管理接口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiCatalogImportRequest, AiProviderCreateRequest, AiProviderRead, AiProviderTestRequest, AiProviderUpdateRequest
from app.modules.ai.service.ai_service import AiProviderService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="provider",
        scope="admin",
        service=AiProviderService,
        tags=("ai", "provider"),
        code_prefix="ai_provider",
        list_response_model=AiProviderRead,
        page_item_model=AiProviderRead,
        info_response_model=AiProviderRead,
        add_request_model=AiProviderCreateRequest,
        add_response_model=AiProviderRead,
        update_request_model=AiProviderUpdateRequest,
        update_response_model=AiProviderRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name"),
            field_eq=("adapter", "is_active"),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "sort_order", "code"),
            add_order_by=(OrderByConfig("sort_order", "desc"), OrderByConfig("created_at", "desc")),
        ),
        soft_delete=True,
    )
)
class AiProviderController(BaseController):
    @Post("/test", summary="测试模型厂商连接", permission="ai:provider:test")
    async def test(
        self,
        payload: AiProviderTestRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiProviderService(session).test(payload.id)

    @Post("/catalog", summary="获取模型厂商预设清单", permission="ai:provider:catalog")
    async def catalog(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiProviderService(session).catalog()

    @Post("/importCatalog", summary="导入模型厂商预设", permission="ai:provider:importCatalog")
    async def import_catalog(
        self,
        payload: AiCatalogImportRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiProviderService(session).import_catalog(payload)


router = AiProviderController.router
