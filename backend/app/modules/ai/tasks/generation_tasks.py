"""
AI 生成任务 Celery 执行入口。
"""
from __future__ import annotations

import json
from datetime import datetime

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
from app.modules.ai.service.ai_service import AiModelRuntimeService
from app.modules.media.service.media_service import MediaAssetService


@celery_app.task(name="ai.execute_generation_task")
def execute_ai_generation_task(task_id: int) -> dict:
    with Session(engine) as session:
        task = session.get(AiGenerationTask, task_id)
        if not task:
            return {"success": False, "message": "AI task not found", "taskId": task_id}
        if task.status == "cancelled":
            return {"success": False, "message": "AI task cancelled", "taskId": task_id}

        task.status = "running"
        task.progress = 10
        task.started_at = datetime.utcnow()
        task.error_message = None
        session.add(task)
        session.commit()

        try:
            payload = _loads_payload(task.request_payload)
            result = _invoke_runtime(session, task, payload)
            session.refresh(task)
            if task.status == "cancelled":
                task.progress = 100
                task.finished_at = task.finished_at or datetime.utcnow()
                session.add(task)
                session.commit()
                return {"success": False, "message": "AI task cancelled", "taskId": task.id}
            task.status = "success"
            task.progress = 100
            task.result_payload = json.dumps(result, ensure_ascii=False, default=str)
            task.finished_at = datetime.utcnow()
            session.add(task)
            session.commit()
            MediaAssetService(session).create_from_ai_task(task)
            return {"success": True, "taskId": task.id}
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = str(exc)[:1000]
            task.finished_at = datetime.utcnow()
            session.add(task)
            session.commit()
            return {"success": False, "taskId": task.id, "message": str(exc)}


def _invoke_runtime(session: Session, task: AiGenerationTask, payload: dict) -> dict:
    runtime = AiModelRuntimeService(session)
    common = {
        "scenario": task.scenario,
        "profile_code": task.profile_code,
        "options": payload.get("options") or {},
    }
    if task.task_type == "chat":
        return runtime.chat(AiChatRequest(**{**common, "messages": payload.get("messages") or []}))
    if task.task_type == "embedding":
        return runtime.embedding(AiEmbeddingRequest(**{**common, "input": payload.get("input")}))
    if task.task_type == "image":
        return runtime.image(AiImageRequest(**{**common, "prompt": payload.get("prompt") or ""}))
    if task.task_type == "rerank":
        return runtime.rerank(AiRerankRequest(**{**common, "query": payload.get("query") or "", "documents": payload.get("documents") or []}))
    if task.task_type == "audio":
        return runtime.audio(AiAudioRequest(**{**common, "input": payload.get("input") or ""}))
    if task.task_type == "video":
        return runtime.video(AiVideoRequest(**{**common, "prompt": payload.get("prompt") or ""}))
    raise ValueError("不支持的 AI 任务类型")


def _loads_payload(value: str | None) -> dict:
    if not value:
        return {}
    data = json.loads(value)
    return data if isinstance(data, dict) else {}
