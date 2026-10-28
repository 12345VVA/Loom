"""agent 运行假死兜底（调用追踪审计 B3）：Celery 周期任务。

背景：agent run 跑在 FastAPI 进程内的 worker 线程（非 Celery）——worker 进程被杀/OOM
后 trace 永久滞留 running，无任何周期收尸（workflow 有 sweep_stuck_instances，agent 此前
没有）。本任务覆盖「进程未重启但线程挂死」与「进程级死亡」两类窗口；与 stop_run 人工
停止、终态必达外圈互补。sweep 逻辑在 maintenance.py（service 层，可直测）；本文件只管
SysParam/会话/日志的 task 装配。
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.database import SessionLocal  # contextmanager（后台任务独立会话）

logger = logging.getLogger("agent.maintenance.tasks")


@celery_app.task(name="agent.maintenance.sweep_stuck_traces")
def sweep_stuck_traces() -> dict:  # noqa: ANN001 —— celery 签名惯例
    from app.modules.agent.service.maintenance import sweep_stuck_traces as sweep_impl
    from app.modules.base.service.sys_manage_service import SysParamService

    grace_minutes = 30
    swept: list[int] = []
    with SessionLocal() as session:
        try:
            raw = SysParamService(session).get_value("agentStuckTraceGraceMinutes", "30")
            grace_minutes = int(raw or 30)
        except Exception:  # noqa: BLE001 —— SysParam 不可用降级默认宽限
            logger.warning("agentStuckTraceGraceMinutes 读取失败，按默认 30 分钟", exc_info=True)
        swept = sweep_impl(session, grace_minutes)
    if swept:
        logger.warning("agent 假死 trace 回收 grace_minutes=%s swept=%s", grace_minutes, swept)
    return {"sweptTraces": len(swept), "graceMinutes": grace_minutes, "sweepIds": swept}
