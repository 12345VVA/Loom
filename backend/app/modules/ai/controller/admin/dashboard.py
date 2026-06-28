"""
AI 成本看板接口。
"""

from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiCallStatsRequest
from app.modules.ai.service.stats_service import AiModelCallStatsService
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.security_service import get_current_user


class _NoopService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, None)


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="dashboard",
        scope="admin",
        service=_NoopService,
        tags=("ai", "dashboard"),
        code_prefix="ai_dashboard",
        actions=(),
    )
)
class AiDashboardController(BaseController):
    @Post("/cost", summary="AI 成本看板统计", permission="ai:dashboard:cost")
    async def cost(
        self,
        payload: AiCallStatsRequest | None = None,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        payload = payload or AiCallStatsRequest()
        return AiModelCallStatsService(session).summary(days=payload.days, group_by=payload.group_by)


router = AiDashboardController.router
