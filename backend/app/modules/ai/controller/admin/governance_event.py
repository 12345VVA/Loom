"""
AI 治理事件接口。
"""

from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiGovernanceEventRead, AiGovernanceStatsRequest
from app.modules.ai.service.governance_service import AiGovernanceEventService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="governanceEvent",
        scope="admin",
        service=AiGovernanceEventService,
        tags=("ai", "governance-event"),
        code_prefix="ai_governance_event",
        list_response_model=AiGovernanceEventRead,
        page_item_model=AiGovernanceEventRead,
        info_response_model=AiGovernanceEventRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("event_type", "metric", "message"),
            field_eq=(
                "rule_id",
                "user_id",
                "profile_id",
                "model_id",
                "provider_id",
                "event_type",
                "metric",
                "notified",
            ),
            field_like=("event_type", "metric", "message"),
            order_fields=("created_at", "updated_at", "current_value", "limit_value"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        list_query=QueryConfig(
            keyword_like_fields=("event_type", "metric", "message"),
            field_eq=(
                "rule_id",
                "user_id",
                "profile_id",
                "model_id",
                "provider_id",
                "event_type",
                "metric",
                "notified",
            ),
            field_like=("event_type", "metric", "message"),
            order_fields=("created_at", "updated_at", "current_value", "limit_value"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AiGovernanceEventController(BaseController):
    @Post("/stats", summary="AI 治理事件统计", permission="ai:governanceEvent:stats")
    def stats(
        self,
        payload: AiGovernanceStatsRequest | None = None,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        payload = payload or AiGovernanceStatsRequest()
        return AiGovernanceEventService(session).stats(payload.days)


router = AiGovernanceEventController.router
