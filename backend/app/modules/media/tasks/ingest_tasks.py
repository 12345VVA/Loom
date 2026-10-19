"""AI 生成产物媒体转存 Celery 任务（ai↔media 方向解耦，2026-10-18 批次1）。

ai 模块只感知任务名字符串（``media.ingest_ai_task``），不 import 本模块；
转存失败重试 3 次（指数退避，仿 mirror_media_asset），重试耗尽仅 Warning——
转存属增强副作用，绝不把失败传染给已成功的 AI 任务。
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.database import Session, engine
from app.modules.media.service.ingest_service import ingest_ai_task_now, sweep_uningested_tasks

logger = logging.getLogger(__name__)


@celery_app.task(name="media.ingest_ai_task", bind=True, max_retries=3)
def ingest_ai_task(self, task_id: int) -> dict:
    """按 AI 任务 id 转存产物到媒体库（幂等；已落资产直接跳过）。"""
    try:
        with Session(engine) as session:
            return ingest_ai_task_now(session, task_id)
    except Exception as exc:
        retries = self.request.retries or 0
        if retries >= self.max_retries:
            logger.warning("AI 产物媒体转存重试耗尽放弃 task_id=%s: %s", task_id, exc)
            return {"success": False, "taskId": task_id}
        countdown = min(60 * (2**retries), 600)
        logger.warning(
            "AI 产物媒体转存失败将重试 task_id=%s 第 %s 次（%ss 后）: %s", task_id, retries + 1, countdown, exc
        )
        raise self.retry(exc=exc, countdown=countdown) from exc


@celery_app.task(name="media.ingest.sweep_uningested")
def sweep_uningested_media_ingest() -> dict:
    """补偿扫描：success 但从未落资产的 AI 任务补派转存（兜底派发丢失）。"""
    return sweep_uningested_tasks()
