"""
AI 生成任务 Celery 执行入口。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.celery_app import celery_app
from app.core.database import Session, engine
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiGenerationTask,
    AiImageRequest,
    AiRerankRequest,
    AiVideoRequest,
)
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.base.model.auth import User
from app.modules.media.service.media_service import MediaAssetService

logger = logging.getLogger(__name__)


@celery_app.task(name="ai.execute_generation_task")
def execute_ai_generation_task(task_id: int) -> dict:
    with Session(engine) as session:
        task = session.get(AiGenerationTask, task_id)
        if not task:
            return {"success": False, "message": "AI task not found", "taskId": task_id}
        if task.status == "cancelled":
            return {"success": False, "message": "AI task cancelled", "taskId": task_id}

        # CAS pending→running：并发重试或重复入队时，仅一个 worker 抢占成功，其余直接跳过，
        # 避免同一任务被重复执行（重复调用 LLM / 重复扣费 / 重复转存媒体）
        claimed = session.execute(
            update(AiGenerationTask)
            .where(AiGenerationTask.id == task_id, AiGenerationTask.status == "pending")
            .values(status="running", progress=10, started_at=datetime.now(timezone.utc), error_message=None)
        )
        if claimed.rowcount == 0:
            logger.info(
                "AI 任务已被其它 worker 接走或非 pending，跳过执行",
                extra={"task_id": task_id, "status": task.status},
            )
            return {"success": False, "message": "AI task already taken", "taskId": task_id}
        session.commit()
        task = session.get(AiGenerationTask, task_id)
        logger.info(
            "AI 异步生成任务开始执行",
            extra={
                "task_id": task.id,
                "task_type": task.task_type,
                "scenario": task.scenario,
                "profile_code": task.profile_code,
            },
        )

        try:
            payload = _loads_payload(task.request_payload)
            logger.info(
                "AI 异步生成任务载入请求完成",
                extra={
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "payload_keys": sorted(payload.keys()),
                    "options_keys": sorted((payload.get("options") or {}).keys()),
                },
            )
            result = _invoke_runtime(session, task, payload)
            logger.info(
                "AI 异步生成任务运行时调用完成",
                extra={
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "profile": result.get("profile"),
                    "request_id": result.get("requestId"),
                },
            )
            session.refresh(task)
            if task.status == "cancelled":
                task.progress = 100
                task.finished_at = task.finished_at or datetime.now(timezone.utc)
                session.add(task)
                session.commit()
                return {"success": False, "message": "AI task cancelled", "taskId": task.id}
            task.status = "success"
            task.progress = 100
            task.result_payload = json.dumps(result, ensure_ascii=False, default=str)
            task.finished_at = datetime.now(timezone.utc)
            session.add(task)
            session.commit()
            logger.info("AI 异步生成任务结果已持久化", extra={"task_id": task.id, "task_type": task.task_type})
            MediaAssetService(session).create_from_ai_task(task)
            logger.info("AI 异步生成任务媒体转存完成", extra={"task_id": task.id, "task_type": task.task_type})
            return {"success": True, "taskId": task.id}
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = str(exc)[:1000]
            task.finished_at = datetime.now(timezone.utc)
            session.add(task)
            session.commit()
            logger.error(
                "AI 异步生成任务执行失败",
                extra={
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "profile_code": task.profile_code,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                exc_info=exc,
            )
            return {"success": False, "taskId": task.id, "message": str(exc)}


def _invoke_runtime(session: Session, task: AiGenerationTask, payload: dict) -> dict:
    runtime = AiModelRuntimeService(session)
    current_user = session.get(User, task.created_by) if task.created_by else None
    common = {
        "scenario": task.scenario,
        "profile_code": task.profile_code,
        "options": payload.get("options") or {},
    }
    if task.task_type == "chat":
        return runtime.chat(
            AiChatRequest(**{**common, "messages": payload.get("messages") or []}),
            current_user=current_user,
            task_id=task.id,
        )
    if task.task_type == "embedding":
        return runtime.embedding(
            AiEmbeddingRequest(**{**common, "input": payload.get("input")}),
            current_user=current_user,
            task_id=task.id,
        )
    if task.task_type == "image":
        return runtime.image(
            AiImageRequest(**{**common, "prompt": payload.get("prompt") or "", "image": payload.get("image")}),
            current_user=current_user,
            task_id=task.id,
        )
    if task.task_type == "rerank":
        return runtime.rerank(
            AiRerankRequest(
                **{**common, "query": payload.get("query") or "", "documents": payload.get("documents") or []}
            ),
            current_user=current_user,
            task_id=task.id,
        )
    if task.task_type == "audio":
        return runtime.audio(
            AiAudioRequest(**{**common, "input": payload.get("input") or ""}),
            current_user=current_user,
            task_id=task.id,
        )
    if task.task_type == "video":
        return runtime.video(
            AiVideoRequest(**{**common, "prompt": payload.get("prompt") or ""}),
            current_user=current_user,
            task_id=task.id,
        )
    raise ValueError("不支持的 AI 任务类型")


def _loads_payload(value: str | None) -> dict:
    if not value:
        return {}
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


@celery_app.task(name="ai.clean_expired_governance_data")
def clean_expired_governance_data() -> dict:
    from app.modules.ai.service.cleanup_service import AiGovernanceCleanupService
    from app.modules.base.service.sys_manage_service import SysParamService

    with Session(engine) as session:
        params = SysParamService(session)
        task_days = _int_param(params.get_value("aiTaskPayloadKeepDays", "90"), 90)
        log_days = _int_param(params.get_value("aiCallLogKeepDays", "180"), 180)
        event_days = _int_param(params.get_value("aiGovernanceEventKeepDays", "180"), 180)
        return AiGovernanceCleanupService(session).clean(task_days, log_days, event_days)


def _int_param(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default
