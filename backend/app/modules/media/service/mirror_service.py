"""媒体产物 TOS/S3 异步镜像服务（WFI-3b，双轨存储模式 B）。

核心约束（多模态一期报告 §5.3）：
- **非阻塞 + 故障隔离**：本地落盘即转存成功；镜像派发/上传/回写任何失败均仅
  Warning 日志，绝不影响主流程（AI 任务/工作流实例状态不因镜像而变）；
- **幂等**：remote_url 已存在的行直接跳过；重试覆盖写无害（对象键按 uuid 新生成，
  旧对象由 bucket 生命周期规则回收）；
- 上传实现独立于 StorageService 主实例（不绑 S3_BUCKET）：直接 ``MEDIA_MIRROR_BUCKET``，
  凭证复用 S3_* 组。传输按端点自动分派：TOS 原生端点（``tos-cn-beijing.volces.com``）
  走 ``tos`` SDK（2026-10-12 真机验证：ark 自动桶不支持 S3 兼容网关，报
  InvalidPathAccess），其余 S3 兼容端点走 boto3。对象键 ``assets/{yyyy}/{mm}/{uuid}{ext}``
  （长期保留区）；``wf-temp/`` 前缀保留给阶段四 Ingress 临时中转（bucket 端 30 天生命周期）。
- TOS 原生上传显式设公共读 ACL：桶默认私有，不设 ACL 时公网大模型拉图 403
  （AromaMemoir 生产验证过的教训），匿名可读是 remote_url 存在的前提。
- 公网 URL：``MEDIA_MIRROR_PUBLIC_BASE_URL`` 优先（CDN/自定义域），缺省按
  对象存储虚拟主机域名 ``https://{bucket}.{endpoint_host}/{key}`` 拼接。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_tos_native_endpoint(endpoint_url: str) -> bool:
    """TOS 原生端点（``tos-{region}.volces.com``）判定；``tos-s3-*`` 兼容端点与其余 S3 走 boto3。"""
    host = endpoint_url.split("://", 1)[-1].split("/", 1)[0].strip("/").lower()
    return host.startswith("tos-") and not host.startswith("tos-s3-")


def dispatch_media_mirror(asset_id: int | None) -> None:
    """转存成功后派发镜像任务。开关关闭直接返回；派发异常仅 Warning（不阻断主流程）。"""
    if not settings.MEDIA_MIRROR_ENABLED or not asset_id:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task("media.mirror_asset", args=[asset_id], queue=settings.MEDIA_MIRROR_QUEUE)
        logger.info("媒体镜像任务已派发 asset_id=%s", asset_id)
    except Exception:
        logger.warning("媒体镜像任务派发失败 asset_id=%s（不影响主流程）", asset_id, exc_info=True)


class MediaMirrorService:
    """镜像执行体（Celery 任务内调用；单测可直接实例化）。"""

    def run(self, asset_id: int) -> dict:

        from app.core.database import SessionLocal
        from app.modules.media.model.media import MediaAsset

        with SessionLocal() as session:
            asset = session.get(MediaAsset, asset_id)
            if asset is None or asset.delete_time is not None:
                return {"skipped": True, "reason": "资产不存在或已删除"}
            if not asset.storage_url or asset.status != "success":
                return {"skipped": True, "reason": "资产无本地地址或未成功转存"}
            if asset.remote_url:
                return {"skipped": True, "reason": "已镜像", "remoteUrl": asset.remote_url}

            content = self._read_local_content(asset.storage_url)
            remote_url = self.upload_mirror_object(
                content, asset.file_name or "", mime_type=asset.mime_type, source_path=asset.storage_url
            )
            asset.remote_url = remote_url
            session.add(asset)
            session.commit()
            logger.info("媒体镜像成功 asset_id=%s → %s", asset_id, remote_url)
            return {"remoteUrl": remote_url}

    @staticmethod
    def _read_local_content(storage_url: str) -> bytes:
        """读回本地（或主存储）字节。相对 /uploads 路径与 S3 主存储统一经 StorageService。"""
        from app.framework.storage import StorageService

        return StorageService.get_instance().read(storage_url)

    def upload_mirror_object(
        self,
        content: bytes,
        filename: str,
        *,
        mime_type: str | None = None,
        source_path: str = "",
        prefix: str = "assets",
    ) -> str:
        """上传镜像对象并返回公网可访问 URL。

        独立 client + 独立 bucket（MEDIA_MIRROR_BUCKET，缺省回落 S3_BUCKET）；
        无扩展名时从 source_path 推断。prefix 区分生命周期：``assets/`` 长期保留
        （产物镜像），``wf-temp/`` 临时中转（bucket 端 30 天过期，WFI-4a Ingress 用）。
        传输按端点自动分派（TOS 原生 SDK / boto3 S3 兼容）。此方法为可 patch 边界（单测锚点）。
        """
        bucket = settings.MEDIA_MIRROR_BUCKET or settings.S3_BUCKET
        if not bucket:
            raise RuntimeError("镜像 bucket 未配置（MEDIA_MIRROR_BUCKET / S3_BUCKET 均为空）")

        ext = os.path.splitext(filename)[1].lower()
        if not ext and source_path:
            ext = os.path.splitext(source_path)[1].lower()
        date_folder = datetime.now().strftime("%Y/%m")
        object_key = f"{prefix}/{date_folder}/{uuid.uuid4().hex}{ext or '.bin'}"

        if _is_tos_native_endpoint(settings.S3_ENDPOINT_URL):
            self._put_tos_native(bucket, object_key, content, mime_type)
        else:
            self._put_s3_compat(bucket, object_key, content, mime_type)

        base = (settings.MEDIA_MIRROR_PUBLIC_BASE_URL or "").rstrip("/")
        if base:
            return f"{base}/{object_key}"
        if settings.S3_ENDPOINT_URL:
            host = settings.S3_ENDPOINT_URL.split("://", 1)[-1].rstrip("/")
            return f"https://{bucket}.{host}/{object_key}"
        return f"https://{bucket}.s3.amazonaws.com/{object_key}"

    @staticmethod
    def _put_tos_native(bucket: str, object_key: str, content: bytes, mime_type: str | None) -> None:
        """TOS 原生 SDK 上传（ark 自动桶等不被 S3 兼容网关服务的桶）。显式公共读 ACL。"""
        import tos

        client = tos.TosClientV2(
            settings.S3_ACCESS_KEY_ID,
            settings.S3_SECRET_ACCESS_KEY,
            settings.S3_ENDPOINT_URL.split("://", 1)[-1].rstrip("/"),
            settings.S3_REGION or "cn-beijing",
        )
        kwargs: dict = {"acl": tos.ACLType.ACL_Public_Read}
        if mime_type:
            kwargs["content_type"] = mime_type
        client.put_object(bucket, object_key, content=content, **kwargs)

    @staticmethod
    def _put_s3_compat(bucket: str, object_key: str, content: bytes, mime_type: str | None) -> None:
        """boto3 S3 兼容上传（MinIO/R2/标准 S3 及 tos-s3-* 兼容端点）。"""
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
            region_name=settings.S3_REGION or None,
        )
        extra_args: dict = {}
        if mime_type:
            extra_args["ContentType"] = mime_type
        client.put_object(Bucket=bucket, Key=object_key, Body=content, **extra_args)
