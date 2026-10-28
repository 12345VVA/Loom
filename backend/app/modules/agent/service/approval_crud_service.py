"""HITL 审批行（AgentToolApproval）管理面只读服务：决定/恢复/核对端点见控制器。

args_json 不出列的治理在 Read DTO（面上只有摘要与 hash）；列表/详情走标准 CRUD 面。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.modules.base.service.admin_service import BaseAdminCrudService


class ApprovalCrudService(BaseAdminCrudService):
    """agent_tool_approval 审批队列（page/info/list；decide 等动作在控制器）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentToolApproval

        super().__init__(session, model or AgentToolApproval)

    def _finalize_data(self, data: Any) -> Any:
        """出口治理：args_json 永不出管理面（仅摘要与 hash；原文只服务执行链）。

        page 传入的是 list[dict]、info 是单 dict（真机 500 根因：原实现按单 dict pop）；
        尾调 super 保留基类 camelCase 出口转换（对齐 profile_service 先例）。
        """
        rows = data if isinstance(data, list) else [data]
        for item in rows:
            if isinstance(item, dict):
                item.pop("argsJson", None)
                item.pop("args_json", None)
        return super()._finalize_data(data)
