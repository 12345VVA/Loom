"""会话（AgentSession）服务：本人限定列表；对象级权限（属主/一致性/隔离）在 P5 收口。"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.base.service.admin_service import BaseAdminCrudService


class AgentSessionService(BaseAdminCrudService):
    """agent_session：列表/详情仅本人（会话属主，验收 21）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentSession

        super().__init__(session, model or AgentSession)

    def _apply_query(self, statement, model, query, current_user=None, **kwargs):
        statement = super()._apply_query(statement, model, query, current_user, **kwargs)
        if current_user is not None:
            statement = statement.where(model.user_id == current_user.id)
        return statement
