"""智能体会话管理 API：会话列表/详情（本人限定）+ messages 消息轨迹。"""

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.framework.router.route_meta import Get
from app.modules.agent.model.agent import (
    AgentMessage,
    AgentMessageRead,
    AgentSession,
    AgentSessionRead,
)
from app.modules.agent.service.runtime.session_service import AgentSessionService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="session",
        scope="admin",
        service=AgentSessionService,
        tags=("agent", "session"),
        code_prefix="agent_session",
        list_response_model=AgentSessionRead,
        page_item_model=AgentSessionRead,
        info_response_model=AgentSessionRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("title", "session_code"),
            field_eq=(
                QueryFieldConfig("profile_id", "profileId"),
                QueryFieldConfig("run_mode", "runMode"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AgentSessionController(BaseController):
    @Get("/messages", summary="会话消息轨迹（仅属主；含工具调用配对）")
    def messages(
        self,
        session_id: int,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[AgentMessageRead]:
        row = session.get(AgentSession, session_id)
        if row is None or row.delete_time is not None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if row.user_id != current_user.id:  # 会话属主（对象级权限）
            raise HTTPException(status_code=403, detail="仅会话属主可查看消息")
        rows = session.exec(
            select(AgentMessage).where(AgentMessage.session_id == session_id).order_by(AgentMessage.id.asc())
        ).all()
        return [AgentMessageRead.model_validate(r) for r in rows]


router = AgentSessionController.router
