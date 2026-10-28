"""HITL 工具审批状态机（E4，二批 3.5）。

职责边界：
- 本文件只管审批行的状态变更（创建/决定/过期/清理）与组 gate 判定——不 spawn 执行；
  恢复执行的编排（claim trace → 重取锁 → 重建载荷 → 组处置 → graph 续跑）在 run_service
  （需要模型/执行器/图全套依赖），由 controller / celery 任务在状态变更后调用 resume_trace；
- 条件更新 everywhere：pending → approved/rejected/expired/cancelled 全部
  ``UPDATE ... WHERE status='pending'``——天然幂等，重启/多 worker 重复扫描安全（A15/A34）；
- args_json 治理：审批面 Read DTO 不出列（面上只有摘要与 hash）；终局超保留期清理置 NULL；
  存储加密待密钥管理基建（记录偏差，见设计补遗跟进项）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_APPROVAL_CANCELLED,
    AGENT_APPROVAL_DECIDED_STATUSES,
    AGENT_APPROVAL_EXECUTING,
    AGENT_APPROVAL_EXPIRED,
    AGENT_APPROVAL_FAILED,
    AGENT_APPROVAL_PENDING,
    AGENT_APPROVAL_SUCCEEDED,
    AGENT_APPROVAL_TERMINAL_STATUSES,
    AGENT_TOOL_LEVEL_DANGEROUS_WRITE,
    AgentToolApproval,
)

logger = logging.getLogger("agent.approval")

# SLA（R-B9）：pending 审批默认 7 天过期；租约 10 分钟（> 工具级超时上界）；args 保留 7 天
APPROVAL_SLA_SECONDS = 7 * 86400
APPROVAL_LEASE_SECONDS = 600
APPROVAL_ARGS_RETENTION_DAYS = 7

# 需审批的风险等级（D11：高风险写必须人工确认；按当前注册 level 实时判定，D14）
APPROVAL_REQUIRED_LEVELS = {AGENT_TOOL_LEVEL_DANGEROUS_WRITE}

# E4 冻结总开关（复核 N-1）：发布六关禁 dangerous_write → 审批链天然不可达；但发起段
# has_pending 409 仍活跃——遗留 pending 行在巡检停跑后无自愈路径，会话永久锁死。
# False = 一个开关控四端（approval_required_for / has_pending / sweep_approvals /
# create_group），解冻 = 改这一处 + 恢复 celery beat 的 sweep-agent-approval-expiry 项。
APPROVAL_CHAIN_ENABLED = False


def utcnow() -> datetime:
    return datetime.now(UTC)


def args_hash_of(args: dict) -> str:
    """审批锚点哈希（A14）：恢复执行前比对，漂移即 fail-close。"""
    return hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def approval_required_for(tool_name: str) -> bool:
    """实时判定该工具是否需要审批（当前注册 level；未注册工具不触发审批——走常规拒绝链）。"""
    if not APPROVAL_CHAIN_ENABLED:
        return False  # 冻结态同时控死产生链：_approval_calls 恒空 → ApprovalSuspension 永不 raise
    from app.modules.agent.service.tool_registry import get_tool

    tool = get_tool(tool_name)
    return tool is not None and tool.level in APPROVAL_REQUIRED_LEVELS


def create_group(
    session: Session,
    *,
    trace_id: int,
    session_id: int,
    tool_round: int,
    ai_message: AIMessage,
    snapshot_id: int | None,
    requested_by: int,
) -> str:
    """为挂起轮的需审批 tool_calls 建 pending 行（同一 assistant 响应 = 一个组）。

    返回 group_id；普通调用不建行（恢复处置时按组上下文生成「未执行」结果）。
    组合唯一冲突（同 trace 同轮同 call_id 已有行）属异常态——fail-fast 暴露。
    """
    if not APPROVAL_CHAIN_ENABLED:  # 防御性 fail-fast：当前经 approval_required_for 已不可达，防直调绕过
        raise HTTPException(status_code=409, detail="审批链已冻结")
    import uuid

    group_id = uuid.uuid4().hex
    expires_at = utcnow() + timedelta(seconds=APPROVAL_SLA_SECONDS)
    for call in ai_message.tool_calls or []:
        name = call.get("name") or ""
        if not approval_required_for(name):
            continue
        args = call.get("args") or {}
        session.add(
            AgentToolApproval(
                session_id=session_id,
                trace_id=trace_id,
                tool_call_group_id=group_id,
                tool_round=tool_round,
                tool_call_id=call.get("id") or "",
                tool_name=name,
                args_json=json.dumps(args, ensure_ascii=False, default=str),
                args_summary=json.dumps(args, ensure_ascii=False, default=str)[:500],
                args_hash=args_hash_of(args),
                snapshot_id=snapshot_id,
                status=AGENT_APPROVAL_PENDING,
                requested_by=requested_by,
                expires_at=expires_at,
            )
        )
    session.commit()
    logger.info("审批组挂起 trace=%s group=%s round=%s", trace_id, group_id, tool_round)
    return group_id


def group_rows(session: Session, trace_id: int, group_id: str) -> list[AgentToolApproval]:
    return list(
        session.exec(
            select(AgentToolApproval)
            .where(
                AgentToolApproval.trace_id == trace_id,
                AgentToolApproval.tool_call_group_id == group_id,
            )
            .order_by(AgentToolApproval.id)  # type: ignore[attr-defined]
        ).all()
    )


def suspended_group_of(session: Session, trace_id: int) -> tuple[str, list[AgentToolApproval]] | None:
    """该 trace 当前的挂起组（同会话锁保证执行串行 → 同一时刻至多一个未终局组）。

    语义 = 最新组（按 id 倒序首行归属）；组内是否已全部终局由 gate_satisfied 判定——
    恢复恰恰发生在「组内已 approved 但尚未执行」的形态，不能以 pending/executing 存在与否
    判定组的存在。
    """
    row = session.exec(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.trace_id == trace_id,
            AgentToolApproval.delete_time == None,  # noqa: E711
        )
        .order_by(AgentToolApproval.id.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    if row is None:
        return None
    return row.tool_call_group_id, group_rows(session, trace_id, row.tool_call_group_id)


def has_pending(session: Session, session_id: int) -> bool:
    """会话阻塞检查（发起段）：存在 pending 审批 → 拒绝新 run（解锁=组终局，自然解除）。"""
    if not APPROVAL_CHAIN_ENABLED:
        return False  # 冻结态阻塞端解除：遗留 pending 行不再让会话 409 锁死（复核 N-1）
    row = session.exec(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.session_id == session_id,
            AgentToolApproval.status == AGENT_APPROVAL_PENDING,
            AgentToolApproval.delete_time == None,  # noqa: E711
        )
        .limit(1)
    ).first()
    return row is not None


def decide(session: Session, *, approval_id: int, action: str, current_user: Any) -> AgentToolApproval:
    """审批决定（approve/reject）：审批人 ≠ 请求者 + 条件更新 pending → 决定态（原子）。

    返回更新后的行；gate 满足与否由调用方经 gate_satisfied 判定并触发 resume_trace。
    """
    from sqlalchemy import update

    from app.modules.agent.model.agent import AGENT_APPROVAL_APPROVED, AGENT_APPROVAL_REJECTED

    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action 必须为 approve 或 reject")
    target = AGENT_APPROVAL_APPROVED if action == "approve" else AGENT_APPROVAL_REJECTED
    row = session.get(AgentToolApproval, approval_id)
    if row is None or row.delete_time is not None:
        raise HTTPException(status_code=404, detail="审批不存在")
    if row.requested_by == current_user.id and not getattr(current_user, "is_super_admin", False):
        # 审批人权限不授予请求者（超级管理员治理豁免——管理面既有矩阵）
        raise HTTPException(status_code=403, detail="发起者不能审批自己的调用")
    now = utcnow()
    result = session.execute(  # 条件更新：仅 pending 可流转（并发双 decide 只有一个赢家）
        update(AgentToolApproval)
        .where(AgentToolApproval.id == approval_id, AgentToolApproval.status == AGENT_APPROVAL_PENDING)
        .values(status=target, approver=current_user.id, decided_at=now)
    )
    session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="该审批已被处理（非 pending 状态）")
    session.expire(row)
    return row


def claim_for_execution(session: Session, *, approval_id: int, lease_seconds: int = APPROVAL_LEASE_SECONDS) -> bool:
    """approved → executing + 写租约（恢复执行的原子 claim；False = 已被处理）。"""
    from sqlalchemy import update

    result = session.execute(
        update(AgentToolApproval)
        .where(AgentToolApproval.id == approval_id, AgentToolApproval.status == "approved")
        .values(status=AGENT_APPROVAL_EXECUTING, lease_expires_at=utcnow() + timedelta(seconds=lease_seconds))
    )
    session.commit()
    return bool(result.rowcount)


def finish_execution(session: Session, *, approval_id: int, success: bool, result_summary: str | None) -> None:
    """executing → succeeded/failed（条件语义：仅 executing 可流转；幂等收尾）。"""
    from sqlalchemy import update

    session.execute(
        update(AgentToolApproval)
        .where(AgentToolApproval.id == approval_id, AgentToolApproval.status == AGENT_APPROVAL_EXECUTING)
        .values(
            status=AGENT_APPROVAL_SUCCEEDED if success else AGENT_APPROVAL_FAILED,
            executed_at=utcnow(),
            result_summary=(result_summary or "")[:2000],
        )
    )
    session.commit()


def abort_approved(session: Session, *, approval_id: int, reason: str) -> None:
    """approved → failed（未执行的收口）：args_hash 漂移拒绝 / 组内 blocker 连带收口。

    finish_execution 只流转 executing——approved 行的直接收口走本函数（条件更新，幂等）。
    """
    from sqlalchemy import update

    session.execute(
        update(AgentToolApproval)
        .where(AgentToolApproval.id == approval_id, AgentToolApproval.status == "approved")
        .values(status=AGENT_APPROVAL_FAILED, executed_at=utcnow(), result_summary=reason[:2000])
    )
    session.commit()


def gate_satisfied(session: Session, trace_id: int, group_id: str) -> bool:
    """整组恢复门槛：组内全部行脱离 pending/executing（决定/终局均算——拒绝与过期也是确定的终局）。"""
    rows = group_rows(session, trace_id, group_id)
    if not rows:
        return False
    return all(r.status not in (AGENT_APPROVAL_PENDING, AGENT_APPROVAL_EXECUTING) for r in rows)


def sweep_approvals(session: Session) -> dict:
    """周期巡检（Celery agent.approval 队列；条件更新幂等，重启/多 worker 安全 A34）：

    1. pending 且 expires_at 到期 → expired（条件更新，谁更新到归谁）；
    2. executing 且租约到期 → 记录残留清单（不改状态——人工核对入口，A25）；
    3. 终局行超 args 保留期 → args_json 置 NULL（仅留摘要与 hash）。
    返回需要尝试恢复的 trace_id 列表（由调用方触发 resume_trace）。
    """
    if not APPROVAL_CHAIN_ENABLED:  # 任务注册保留（beat 已停），防手工触发在冻结态流转行状态
        return {"expired": 0, "staleExecuting": [], "argsCleaned": 0, "resumeTraceIds": []}
    now = utcnow()
    expired_traces: set[int] = set()
    expired_count = 0
    pendings = list(
        session.exec(
            select(AgentToolApproval).where(
                AgentToolApproval.status == AGENT_APPROVAL_PENDING,
                AgentToolApproval.expires_at != None,  # noqa: E711
                AgentToolApproval.delete_time == None,  # noqa: E711
            )
        ).all()
    )
    for row in pendings:
        if row.expires_at is None or row.expires_at > now:
            continue
        row.status = AGENT_APPROVAL_EXPIRED
        row.decided_at = now
        session.add(row)
        expired_traces.add(row.trace_id)
        expired_count += 1
    session.commit()

    lease_breached = list(
        session.exec(
            select(AgentToolApproval).where(
                AgentToolApproval.status == AGENT_APPROVAL_EXECUTING,
                AgentToolApproval.lease_expires_at != None,  # noqa: E711
                AgentToolApproval.delete_time == None,  # noqa: E711
            )
        ).all()
    )
    stale = [
        {"id": r.id, "traceId": r.trace_id, "toolName": r.tool_name}
        for r in lease_breached
        if r.lease_expires_at is not None and r.lease_expires_at <= now
    ]
    for item in stale:
        logger.warning("审批执行租约到期仍 executing（残留执行，需人工核对）：%s", item)

    cutoff = now - timedelta(days=APPROVAL_ARGS_RETENTION_DAYS)
    finalized = list(
        session.exec(
            select(AgentToolApproval).where(
                AgentToolApproval.status.in_(AGENT_APPROVAL_TERMINAL_STATUSES),  # type: ignore[attr-defined]
                AgentToolApproval.args_json != None,  # noqa: E711
                AgentToolApproval.delete_time == None,  # noqa: E711
            )
        ).all()
    )
    cleaned = 0
    for row in finalized:
        anchor = row.executed_at or row.decided_at
        if anchor is not None and anchor < cutoff:
            row.args_json = None
            session.add(row)
            cleaned += 1
    session.commit()

    return {
        "expired": expired_count,
        "staleExecuting": stale,
        "argsCleaned": cleaned,
        "resumeTraceIds": sorted(expired_traces),
    }


def cancel_group(session: Session, *, trace_id: int, group_id: str | None = None) -> list[AgentToolApproval]:
    """挂起 run 被取消：组内未终局行 → cancelled（条件语义，幂等）。返回受影响行。"""
    rows = group_rows(session, trace_id, group_id) if group_id else _all_live_rows(session, trace_id)
    affected = []
    for row in rows:
        if row.status in AGENT_APPROVAL_DECIDED_STATUSES or row.status in AGENT_APPROVAL_TERMINAL_STATUSES:
            continue
        row.status = AGENT_APPROVAL_CANCELLED
        row.decided_at = utcnow()
        session.add(row)
        affected.append(row)
    session.commit()
    return affected


def _all_live_rows(session: Session, trace_id: int) -> list[AgentToolApproval]:
    return list(
        session.exec(
            select(AgentToolApproval).where(
                AgentToolApproval.trace_id == trace_id,
                AgentToolApproval.delete_time == None,  # noqa: E711
            )
        ).all()
    )
