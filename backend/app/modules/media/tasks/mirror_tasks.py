"""媒体模块 Celery 任务（WFI-3b）。"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.modules.media.service.mirror_service import MediaMirrorService

logger = logging.getLogger(__name__)


@celery_app.task(name="media.mirror_asset", bind=True, max_retries=3)
def mirror_media_asset(self, asset_id: int) -> dict:
    """媒体产物镜像到 TOS/S3 并回写 remote_url。

    失败重试 3 次（指数退避 60s→120s→240s，封顶 600s）；重试耗尽放弃并仅
    Warning——镜像属增强能力，绝不把主流程的失败传染给资产状态。
    """
    try:
        return MediaMirrorService().run(asset_id)
    except Exception as exc:
        retries = self.request.retries or 0
        if retries >= self.max_retries:
            logger.warning("媒体镜像重试耗尽放弃 asset_id=%s: %s", asset_id, exc)
            return {"failed": True, "assetId": asset_id}
        countdown = min(60 * (2**retries), 600)
        logger.warning("媒体镜像失败将重试 asset_id=%s 第 %s 次（%ss 后）: %s", asset_id, retries + 1, countdown, exc)
        raise self.retry(exc=exc, countdown=countdown)
