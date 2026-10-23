"""run 轨迹（观测）只读服务：trace 管理面仅本人可见（验收 21），管理权限单独设点。"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.base.service.admin_service import BaseAdminCrudService


class AgentRunTraceService(BaseAdminCrudService):
    """agent_run_trace 只读面（trace 详情内含工具明细，P5 收口）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentRunTrace

        super().__init__(session, model or AgentRunTrace)

    def _apply_query(self, statement, model, query, current_user=None, **kwargs):
        """仅本人（验收 21）；管理员亦经专门管理权限查看，此处一律限定 user_id。"""
        statement = super()._apply_query(statement, model, query, current_user, **kwargs)
        if current_user is not None:
            statement = statement.where(model.user_id == current_user.id)
        return statement
