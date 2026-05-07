"""AI 生成任务服务。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.modules.ai.model.ai import AiGenerationTask, AiTaskSubmitRequest
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService


class AiGenerationTaskService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiGenerationTask)

    def submit(self, payload: AiTaskSubmitRequest | dict, current_user: User | None = None) -> dict:
        if isinstance(payload, dict):
            payload = AiTaskSubmitRequest(**payload)
        self._validate_task_type(payload.task_type)
        task = AiGenerationTask(
            task_type=payload.task_type,
            scenario=payload.scenario or "default",
            profile_code=payload.profile_code,
            request_payload=json.dumps(payload.payload, ensure_ascii=False, default=str),
            status="pending",
            progress=0,
            created_by=current_user.id if current_user else None,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        try:
            async_result = execute_ai_generation_task.apply_async(args=(task.id,), queue=f"ai.{task.task_type}")
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = f"任务入队失败: {exc}"[:1000]
            task.finished_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=task.error_message) from exc
        task.celery_task_id = async_result.id
        self.session.add(task)
        self.session.commit()
        return {"success": True, "taskId": task.id, "celeryTaskId": async_result.id}

    def cancel(self, id: int) -> dict:
        task = self.session.get(AiGenerationTask, id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 任务不存在")
        if task.status in {"success", "failed", "cancelled"}:
            return {"success": True, "status": task.status}
        if task.celery_task_id:
            from app.celery_app import celery_app

            try:
                celery_app.control.revoke(task.celery_task_id, terminate=True)
            except Exception:
                pass
        task.status = "cancelled"
        task.progress = 100
        task.finished_at = datetime.utcnow()
        self.session.add(task)
        self.session.commit()
        return {"success": True, "status": task.status}

    def retry(self, id: int) -> dict:
        task = self.session.get(AiGenerationTask, id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 任务不存在")
        if task.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅失败或已取消任务可以重试")
        task.status = "pending"
        task.progress = 0
        task.result_payload = None
        task.error_message = None
        task.started_at = None
        task.finished_at = None
        task.retry_count += 1
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        try:
            async_result = execute_ai_generation_task.apply_async(args=(task.id,), queue=f"ai.{task.task_type}")
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = f"任务入队失败: {exc}"[:1000]
            task.finished_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=task.error_message) from exc
        task.celery_task_id = async_result.id
        self.session.add(task)
        self.session.commit()
        return {"success": True, "taskId": task.id, "celeryTaskId": async_result.id}

    def stats(self) -> dict:
        rows = self.session.exec(select(AiGenerationTask.status, AiGenerationTask.error_message)).all()
        status_counts: dict[str, int] = {}
        recent_errors: list[str] = []
        for status_value, error_message in rows:
            status_counts[status_value] = status_counts.get(status_value, 0) + 1
            if error_message:
                recent_errors.append(error_message)
        return {"statusCounts": status_counts, "recentErrors": recent_errors[-5:]}

    def _validate_task_type(self, task_type: str) -> None:
        if task_type not in {"chat", "embedding", "image", "rerank", "audio", "video"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的 AI 任务类型")
