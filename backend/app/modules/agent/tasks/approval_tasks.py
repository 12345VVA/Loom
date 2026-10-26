"""agent 审批过期巡检（E4，二批 3.5）：Celery 周期任务。

设计要点（A34）：
- 条件更新幂等（pending → expired 的原子流转）——重启/多 worker 并发扫描不会重复处理同一行；
- 过期行的组若已全部终局 → 尝试恢复（resume_trace 内部再次 gate + claim trace，双保险）；
- 恢复失败（锁占用/已被认领）静默跳过，等下一轮巡检或人工触发。
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.database import SessionLocal  # contextmanager（后台任务独立会话）

logger = logging.getLogger("agent.approval.tasks")


@celery_app.task(name="agent.approval.sweep_expiry", bind=True, max_retries=3, default_retry_delay=30)
def sweep_approval_expiry(self) -> dict:  # noqa: ANN001 —— celery 签名惯例
    from app.modules.agent.service import approval_service
    from app.modules.agent.service.runtime.run_service import AgentRunService

    summary: dict = {"expired": 0, "resumed": 0, "errors": 0}
    with SessionLocal() as session:
        try:
            result = approval_service.sweep_approvals(session)
            summary["expired"] = result["expired"]
            summary["staleExecuting"] = len(result["staleExecuting"])
            summary["argsCleaned"] = result["argsCleaned"]
            for trace_id in result["resumeTraceIds"]:
                try:
                    resumed = AgentRunService(session).resume_trace(trace_id)
                    if resumed.get("resumed"):
                        summary["resumed"] += 1
                except Exception:  # noqa: BLE001 —— 单 trace 恢复失败不影响其余
                    logger.exception("审批过期恢复失败 trace=%s", trace_id)
                    summary["errors"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("审批巡检失败")
            summary["errors"] += 1
            raise self.retry(exc=exc) from exc
    if summary["expired"] or summary.get("staleExecuting") or summary["errors"]:
        logger.info("agent 审批巡检：%s", summary)
    return summary
