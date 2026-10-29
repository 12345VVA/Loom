"""agent run 假死回收（调用追踪审计 B3）：逻辑层，Celery 任务壳见 tasks/maintenance_tasks.py。

语义：只扫 running（waiting_approval 是合法长等态，E4 解冻后审批可等数日）；条件更新
幂等（仅 running 可流转——并发 sweep/人工 stop 谁先谁赢）；终态化 failed + error 标注 +
duration 按 created_at 补算。宽限期由调用方传入（SysParam agentStuckTraceGraceMinutes，
默认 30 分钟）。

updated_at 判据（复核 2026-10-29 问题③修正）：graph 模型/工具节点出口经 heartbeat
闭包显式刷新 updated_at（BaseEntity 无 onupdate，运行中不写则恒停 INSERT 时刻）——
本函数的「updated_at < cutoff」自心跳接入起才真正表达「最后活动后 grace 分钟仍无
推进」；历史行/未接线路径退化为「启动后 grace 分钟」硬上限（偏保守，不漏杀，可能
暂态误标——worker 真完成时 _finish_run 会覆写回 completed，审计终值最终一致）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, select

from app.modules.agent.model.agent import AGENT_RUN_FAILED, AGENT_RUN_RUNNING, AgentRunTrace

logger = logging.getLogger("agent.maintenance")


def sweep_stuck_traces(session: Session, grace_minutes: int) -> list[int]:
    """回收假死 running trace：返回被终态化的 trace_id 列表（幂等，可重复调用）。"""
    cutoff = datetime.now(UTC) - timedelta(minutes=grace_minutes)
    stale = list(
        session.exec(
            select(AgentRunTrace).where(
                AgentRunTrace.status == AGENT_RUN_RUNNING,
                AgentRunTrace.updated_at != None,  # noqa: E711
                AgentRunTrace.updated_at < cutoff,
            )
        ).all()
    )
    swept: list[int] = []
    now = datetime.now(UTC)
    for trace in stale:
        created_at = trace.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)  # SQLite 测试库读回 naive——按 UTC 归一
        result = session.execute(
            update(AgentRunTrace)
            .where(AgentRunTrace.id == trace.id, AgentRunTrace.status == AGENT_RUN_RUNNING)
            .values(
                status=AGENT_RUN_FAILED,
                error=f"worker 假死超时被回收（sweep，宽限 {grace_minutes} 分钟）",
                duration_ms=int((now - created_at).total_seconds() * 1000) if created_at else None,
            )
        )
        if result.rowcount:
            swept.append(trace.id)
    session.commit()
    return swept
