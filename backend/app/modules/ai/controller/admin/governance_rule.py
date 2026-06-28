"""
AI 治理规则接口。
"""

from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import (
    AiGovernanceRuleActionRequest,
    AiGovernanceRuleCreateRequest,
    AiGovernanceRuleMatchRequest,
    AiGovernanceRuleRead,
    AiGovernanceRuleUpdateRequest,
)
from app.modules.ai.service.governance_service import AiGovernanceRuleService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="governanceRule",
        scope="admin",
        service=AiGovernanceRuleService,
        tags=("ai", "governance-rule"),
        code_prefix="ai_governance_rule",
        list_response_model=AiGovernanceRuleRead,
        page_item_model=AiGovernanceRuleRead,
        info_response_model=AiGovernanceRuleRead,
        add_request_model=AiGovernanceRuleCreateRequest,
        add_response_model=AiGovernanceRuleRead,
        update_request_model=AiGovernanceRuleUpdateRequest,
        update_response_model=AiGovernanceRuleRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name"),
            field_eq=("scope_type", "user_id", "profile_id", "period", "mode", "is_active"),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "sort_order", "code"),
            add_order_by=(OrderByConfig("sort_order", "desc"), OrderByConfig("created_at", "desc")),
        ),
        soft_delete=True,
    )
)
class AiGovernanceRuleController(BaseController):
    @Post("/toggle", summary="启停 AI 治理规则", permission="ai:governanceRule:toggle")
    async def toggle(
        self,
        payload: AiGovernanceRuleActionRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGovernanceRuleService(session).toggle(payload.id)

    @Post("/match", summary="测试 AI 治理规则匹配", permission="ai:governanceRule:match")
    async def match(
        self,
        payload: AiGovernanceRuleMatchRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGovernanceRuleService(session).match(payload)


router = AiGovernanceRuleController.router
