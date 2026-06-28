"""AI 治理数据清理服务。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from app.modules.ai.model.ai import AiGenerationTask, AiGovernanceEvent, AiModelCallLog


class AiGovernanceCleanupService:
    def __init__(self, session: Session):
        self.session = session

    def clean(
        self, task_payload_keep_days: int = 90, call_log_keep_days: int = 180, event_keep_days: int = 180
    ) -> dict:
        now = datetime.utcnow()
        task_cutoff = now - timedelta(days=task_payload_keep_days)
        log_cutoff = now - timedelta(days=call_log_keep_days)
        event_cutoff = now - timedelta(days=event_keep_days)
        tasks = self.session.exec(
            select(AiGenerationTask).where(
                AiGenerationTask.created_at < task_cutoff,
                (AiGenerationTask.request_payload != None) | (AiGenerationTask.result_payload != None),  # noqa: E711
            )
        ).all()
        for task in tasks:
            task.request_payload = None
            task.result_payload = None
            self.session.add(task)
        log_result = self.session.exec(delete(AiModelCallLog).where(AiModelCallLog.created_at < log_cutoff))
        event_result = self.session.exec(delete(AiGovernanceEvent).where(AiGovernanceEvent.created_at < event_cutoff))
        self.session.commit()
        # 删除调用日志后失效统计看板缓存（与 _log_call 写入后的失效对齐，避免清理后看板短时陈旧）
        from app.modules.ai.service.stats_service import invalidate_summary_cache

        invalidate_summary_cache()
        return {
            "success": True,
            "taskPayloadCleared": len(tasks),
            "callLogsDeleted": getattr(log_result, "rowcount", 0),
            "governanceEventsDeleted": getattr(event_result, "rowcount", 0),
        }
