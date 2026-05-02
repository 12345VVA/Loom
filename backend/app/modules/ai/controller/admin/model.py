"""
AI 模型管理接口。
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.modules.ai.model.ai import AiModelCreateRequest, AiModelRead, AiModelUpdateRequest
from app.modules.ai.service.ai_service import AiModelService


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="model",
        scope="admin",
        service=AiModelService,
        tags=("ai", "model"),
        code_prefix="ai_model",
        list_response_model=AiModelRead,
        page_item_model=AiModelRead,
        info_response_model=AiModelRead,
        add_request_model=AiModelCreateRequest,
        add_response_model=AiModelRead,
        update_request_model=AiModelUpdateRequest,
        update_response_model=AiModelRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name"),
            field_eq=("provider_id", "model_type", "is_active"),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "sort_order", "code"),
            add_order_by=(OrderByConfig("sort_order", "desc"), OrderByConfig("created_at", "desc")),
        ),
        soft_delete=True,
    )
)
class AiModelController(BaseController):
    pass


router = AiModelController.router
