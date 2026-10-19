"""AI 生成产物落媒体库的统一转存入口（ai↔media 方向解耦，2026-10-18 批次1）。

方向解耦（核实报告 §三3.1/§四批次1）：
- ai 模块不再 import media：异步路径经 Celery 字符串派发（``media.ingest_ai_task``），
  同步路径经 framework runtime 注册表回调（``media_ingest_ai_result``，main.py 装配）；
- 幂等：``source_type='ai_task' + source_task_id`` 已存在资产则跳过，重试/补偿安全；
- 补偿：beat 每小时 sweep（``media.ingest.sweep_uningested``）兜底派发丢失的转存；
- 失败容忍：派发/执行任何失败均不回传 AI 侧（修复原 generation_tasks 转存异常
  翻转已成功任务的结构性隐患，转存与任务状态天然隔离）。
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.modules.ai.model.ai import AiGenerationTask
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService

logger = logging.getLogger(__name__)

MEDIA_INGEST_TASK_NAME = "media.ingest_ai_task"

# 会产出可落库媒体资产的任务类型：chat/embedding/rerank 的结果是文本/向量，
# _extract_artifacts 恒返回 []，若纳入扫描会因「永远没有资产」被 sweep 每小时重复派发
MEDIA_PRODUCING_TASK_TYPES: frozenset[str] = frozenset({"image", "video", "audio"})


def dispatch_media_ingest(task_id: int | None) -> None:
    """派发 AI 产物转存任务。派发异常仅 Warning（不阻断调用方主流程）。"""
    if not task_id:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task(MEDIA_INGEST_TASK_NAME, args=[task_id], queue="default")
        logger.info("AI 产物媒体转存任务已派发 task_id=%s", task_id)
    except Exception:
        logger.warning("AI 产物媒体转存任务派发失败 task_id=%s（不影响主流程）", task_id, exc_info=True)


def _has_ingested_assets(session: Session, task_id: int) -> bool:
    """该 AI 任务是否已落过媒体资产（幂等判据，与 create_from_ai_task 的 source 口径一致）。"""
    statement = select(MediaAsset.id).where(
        MediaAsset.source_type == "ai_task",
        MediaAsset.source_task_id == task_id,
        MediaAsset.delete_time == None,  # noqa: E711
    )
    return session.exec(statement).first() is not None


def ingest_ai_task_now(session: Session, task_id: int) -> dict:
    """按任务 id 执行转存（Celery 任务与 sweep 共用核心）。

    任务不存在/非 success/已落资产均跳过（返回 skipped 口径，不抛错）；
    仅解析与落库的意外异常向上抛，由 Celery 重试机制接管。
    """
    task = session.get(AiGenerationTask, task_id)
    if not task or task.status != "success" or not task.result_payload:
        return {"success": True, "taskId": task_id, "skipped": True}
    if task.task_type not in MEDIA_PRODUCING_TASK_TYPES:
        # 文本类任务（chat/embedding/rerank）无媒体产物，直接跳过（与 sweep 口径一致）
        return {"success": True, "taskId": task_id, "skipped": True}
    if _has_ingested_assets(session, task_id):
        return {"success": True, "taskId": task_id, "skipped": True}
    assets = MediaAssetService(session).create_from_ai_task(task)
    logger.info(
        "AI 产物媒体转存完成",
        extra={"task_id": task_id, "task_type": task.task_type, "asset_count": len(assets)},
    )
    return {"success": True, "taskId": task_id, "skipped": False, "assetIds": [asset.id for asset in assets]}


def sweep_uningested_tasks(limit: int = 200) -> dict:
    """扫描「success 但从未落资产」的 AI 任务并补派转存（beat 兜底，防派发丢失）。"""
    from app.core.database import Session as DbSession
    from app.core.database import engine

    asset_exists = (
        select(MediaAsset.id)
        .where(
            MediaAsset.source_type == "ai_task",
            MediaAsset.source_task_id == AiGenerationTask.id,
            MediaAsset.delete_time == None,  # noqa: E711
        )
        .exists()
    )
    statement = (
        select(AiGenerationTask)
        .where(
            AiGenerationTask.status == "success",
            # 只扫有媒体产物的类型：文本类任务永远不会落资产，纳入后每小时被重复派发
            AiGenerationTask.task_type.in_(tuple(MEDIA_PRODUCING_TASK_TYPES)),
            AiGenerationTask.delete_time == None,  # noqa: E711
            AiGenerationTask.result_payload != None,  # noqa: E711
            ~asset_exists,
        )
        .order_by(AiGenerationTask.id.desc())
        .limit(limit)
    )
    with DbSession(engine) as session:
        rows = list(session.exec(statement).all())
    for row in rows:
        dispatch_media_ingest(row.id)
    if rows:
        logger.info("AI 产物媒体转存补偿扫描派发 %d 条", len(rows))
    return {"success": True, "scanned": len(rows), "taskIds": [row.id for row in rows[:10]]}


def ingest_ai_result_callback(
    session: Session,
    *,
    task_type: str,
    result: dict,
    request_payload: dict,
    source_type: str,
    created_by: int | None = None,
    profile_code: str | None = None,
    **_ignored: object,
) -> int:
    """registry 回调（``media_ingest_ai_result``）：同步调用的 AI 结果转存入口。

    main.py 装配期注册，ai 侧经 registry.resolve 调用（不 import 本模块符号）；
    返回落库资产数供调用方记日志。异常由调用方兜底（不影响生图主流程）。
    """
    assets = MediaAssetService(session).create_from_ai_result(
        task_type=task_type,
        result=result,
        request_payload=request_payload,
        source_type=source_type,
        created_by=created_by,
        profile_code=profile_code,
    )
    return len(assets)


__all__ = [
    "MEDIA_INGEST_TASK_NAME",
    "dispatch_media_ingest",
    "ingest_ai_result_callback",
    "ingest_ai_task_now",
    "sweep_uningested_tasks",
]
