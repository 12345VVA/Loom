"""工具资源层（AgentToolResource）只读服务：启停/刷新端点见控制器（P2 接 tool_registry）。"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.base.service.admin_service import BaseAdminCrudService


class AgentToolResourceService(BaseAdminCrudService):
    """agent_tool_resource 管理面只读（全员可看工具清单；启停为管理员权限点）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentToolResource

        super().__init__(session, model or AgentToolResource)
