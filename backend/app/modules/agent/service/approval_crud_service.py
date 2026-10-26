"""HITL 审批行（AgentToolApproval）管理面只读服务：决定/恢复/核对端点见控制器。

args_json 不出列的治理在 Read DTO（面上只有摘要与 hash）；列表/详情走标准 CRUD 面。
"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.base.service.admin_service import BaseAdminCrudService


class ApprovalCrudService(BaseAdminCrudService):
    """agent_tool_approval 审批队列（page/info/list；decide 等动作在控制器）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentToolApproval

        super().__init__(session, model or AgentToolApproval)

    def _finalize_data(self, data: dict) -> dict:
        """出口治理：args_json 永不出管理面（仅摘要与 hash；原文只服务执行链）。"""
        data.pop("argsJson", None)
        data.pop("args_json", None)
        return data
