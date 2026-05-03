"""
AI 模型调用日志接口。
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.modules.ai.model.ai import AiModelCallLogRead
from app.modules.ai.service.ai_service import AiModelCallLogService


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="log",
        scope="admin",
        service=AiModelCallLogService,
        tags=("ai", "log"),
        code_prefix="ai_log",
        list_response_model=AiModelCallLogRead,
        page_item_model=AiModelCallLogRead,
        info_response_model=AiModelCallLogRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("scenario", "status", "model_type", "request_id", "error_message"),
            field_eq=("provider_id", "model_id", "profile_id", "scenario", "model_type", "status"),
            field_like=("scenario", "request_id", "error_message"),
            order_fields=("created_at", "updated_at", "latency_ms", "total_tokens"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        list_query=QueryConfig(
            keyword_like_fields=("scenario", "status", "model_type", "request_id", "error_message"),
            field_eq=("provider_id", "model_id", "profile_id", "scenario", "model_type", "status"),
            field_like=("scenario", "request_id", "error_message"),
            order_fields=("created_at", "updated_at", "latency_ms", "total_tokens"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AiModelCallLogController(BaseController):
    pass


router = AiModelCallLogController.router
