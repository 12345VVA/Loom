"""HITL 工具审批管理面（E4）：审批队列 / 决定 / 租约残留人工核对。

- decide：审批人 ≠ 请求者（approval_service 强制）；成功后 gate 满足即触发 resume_trace；
- reconcile：executing 且租约到期（残留执行，A25）的人工标记收口；retry 仅只读工具
  （当前注册 level 判定——写工具永不自动/手动代执行，D11）。
"""

from typing import Any

from fastapi import Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.framework.router.route_meta import Post
from app.modules.agent.model.agent import (
    AGENT_APPROVAL_EXECUTING,
    AGENT_APPROVAL_SUCCEEDED,
    AgentToolApproval,
    AgentToolApprovalRead,
    ApprovalDecideRequest,
    ApprovalReconcileRequest,
)
from app.modules.agent.service import approval_service
from app.modules.agent.service.approval_crud_service import ApprovalCrudService
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user

_PERM = "agent:approval"


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="approval",
        scope="admin",
        service=ApprovalCrudService,
        tags=("agent", "approval"),
        code_prefix="agent_approval",
        list_response_model=AgentToolApprovalRead,
        page_item_model=AgentToolApprovalRead,
        info_response_model=AgentToolApprovalRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("tool_name",),
            field_eq=(
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("session_id", "sessionId"),
                QueryFieldConfig("trace_id", "traceId"),
                QueryFieldConfig("requested_by", "requestedBy"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AgentApprovalController(BaseController):
    @Post("/decide", summary="审批决定（approve/reject；审批人≠请求者；组终局自动恢复）", permission=f"{_PERM}:decide")
    def decide(
        self,
        payload: ApprovalDecideRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        row = approval_service.decide(session, approval_id=payload.id, action=payload.action, current_user=current_user)
        resumed = AgentRunService(session).resume_trace(row.trace_id)
        return {"ok": True, "status": row.status, "resume": resumed}

    @Post("/reconcile", summary="租约残留人工核对收口（标记 succeeded/failed）", permission=f"{_PERM}:reconcile")
    def reconcile(
        self,
        payload: ApprovalReconcileRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        if payload.outcome not in (AGENT_APPROVAL_SUCCEEDED, "failed"):
            raise HTTPException(status_code=400, detail="outcome 必须为 succeeded 或 failed")
        row = session.get(AgentToolApproval, payload.id)
        if row is None or row.delete_time is not None:
            raise HTTPException(status_code=404, detail="审批不存在")
        if row.status != AGENT_APPROVAL_EXECUTING:
            raise HTTPException(status_code=409, detail="仅 executing 状态可人工核对收口")
        approval_service.finish_execution(
            session,
            approval_id=row.id,
            success=payload.outcome == AGENT_APPROVAL_SUCCEEDED,
            result_summary=f"[人工核对 by {current_user.id}] {payload.note or ''}",
        )
        resumed = AgentRunService(session).resume_trace(row.trace_id)
        return {"ok": True, "status": row.status, "resume": resumed}

    @Post("/retry", summary="只读工具残留重试（写工具永不重试，D11）", permission=f"{_PERM}:reconcile")
    def retry(
        self,
        payload: ApprovalReconcileRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        from app.modules.agent.service.tool_registry import get_tool

        row = session.get(AgentToolApproval, payload.id)
        if row is None or row.delete_time is not None:
            raise HTTPException(status_code=404, detail="审批不存在")
        if row.status != AGENT_APPROVAL_EXECUTING:
            raise HTTPException(status_code=409, detail="仅 executing 状态可重试")
        tool = get_tool(row.tool_name)
        if tool is None or tool.level != "readonly":
            raise HTTPException(status_code=403, detail="仅只读工具可重试（写工具残留须人工核对标记结果）")
        args: dict = {}
        if row.args_json:
            import json as _json

            try:
                args = _json.loads(row.args_json)
            except ValueError:
                args = {}
        import time as _time

        started = _time.monotonic()
        try:
            result = tool.func(tool.args_model.model_validate(args), _ReconcileCtx(session, row.requested_by))
            content = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False)
            approval_service.finish_execution(session, approval_id=row.id, success=True, result_summary=content[:2000])
            ok = True
        except Exception as exc:  # noqa: BLE001 —— 重试失败照实记 failed
            approval_service.finish_execution(
                session, approval_id=row.id, success=False, result_summary=f"[重试失败] {exc}"[:2000]
            )
            ok = False
        _ = int((_time.monotonic() - started) * 1000)
        resumed = AgentRunService(session).resume_trace(row.trace_id)
        return {"ok": ok, "resume": resumed}


class _ReconcileCtx:
    """重试执行的最小 ToolContext（以原请求者身份；顺序同步使用请求 Session）。"""

    def __init__(self, db: Any, user_id: int):
        self.db = db
        self.user_id = user_id
        self.user_name = ""
        self.is_super_admin = False
        self.trace_id = None
        self.run_mode = ""


router = AgentApprovalController.router
