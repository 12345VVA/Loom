"""图片 URL 消费调度（媒体域公共能力；原 WFI-4a，自 workflow 模块整体下沉）。

把业务内流转的图片引用解析为「当前消费场景最优 URL」，统一决策表：

1. 公网 http(s) URL / data URI → 原样返回（显式引用 ``__src`` 厂商临时 URL 的
   既有工作流天然短路，零影响）；
2. ``/uploads`` 相对路径（本地落盘资产）：
   a. ``prefer_remote`` 且 ``MediaAsset.remote_url`` 已回写 → 直接返回
      （阶段三镜像产物，0 搬运、同机房直连）；
   b. 配置了 ``BACKEND_URL`` / ``EXTERNAL_URL`` 公网域名 → ``make_absolute_url``
      拼接返回；
   c. 均不可用（纯私网/开发环境兜底地址）且镜像存储可用（MEDIA_MIRROR_ENABLED +
      bucket）→ 读本地字节经 ``wf-temp/`` 前缀中转上传，返回免签公网 URL
      （bucket 端配置 30 天生命周期控制费用）；
   d. 全部不可用 → 抛 ``ValueError``（情景 C：节点执行期友好报错，替代此前
      「拼出 127.0.0.1 发给厂商、上游报错才暴露」的晚失败）。

调用点：workflow execute_image_generator_node（参考图）/ execute_llm_node（IR parts）；
asset 模块（IP 资产库）参考图注入复用同款调度（决策 #19，设计文档 3.5）。
含 DB 查询与潜在网络 IO，调用方应经 ``asyncio.to_thread`` 包裹。
"""

from __future__ import annotations

import logging
import os

from app.core.config import settings
from app.modules.ai.service.runtime_service import make_absolute_url

logger = logging.getLogger(__name__)

_SCENARIO_C_MESSAGE = (
    "图片为本地路径且当前部署无公网访问能力（BACKEND_URL/EXTERNAL_URL 未配置、"
    "对象存储镜像未启用），云端模型无法拉取。请配置对象存储（MEDIA_MIRROR_*）"
    "或 EXTERNAL_URL，或直接传入公网图片 URL"
)


def resolve_consumable_image_url(image_ref: str, *, prefer_remote: bool = True) -> str:
    """单值解析：按模块 docstring 决策表返回可消费 URL，情景 C 抛 ValueError。"""
    if not image_ref:
        return image_ref
    # 1. 公网 URL / data URI 直传短路（不查库、不落网）
    if image_ref.startswith(("http://", "https://", "data:")):
        return image_ref

    # 2. 本地相对路径
    if image_ref.startswith("/"):
        # 2a. 镜像直链优先（0 搬运）
        if prefer_remote:
            remote = _lookup_remote_url(image_ref)
            if remote:
                return remote
        # 2b. 公网域名拼接（BACKEND_URL > EXTERNAL_URL，与 make_absolute_url 同判定：
        # 二者均未配置时其兜底是 host:port 私网地址，厂商不可达）
        if settings.BACKEND_URL or settings.EXTERNAL_URL:
            return make_absolute_url(image_ref)
        # 2c. wf-temp/ 临时中转（镜像存储可用时）
        transit = _ingress_transit(image_ref)
        if transit:
            return transit
        # 2d. 情景 C：显式友好失败
        raise ValueError(_SCENARIO_C_MESSAGE)

    # 非 / 开头的裸相对路径：规范提醒后按情景 C 处理（上游传值应规范为 / 开头）
    raise ValueError(f"图片路径需以 / 开头（收到: {image_ref[:80]}）；{_SCENARIO_C_MESSAGE}")


def resolve_image_input_value(value: str | list[str] | None, *, prefer_remote: bool = True) -> str | list[str] | None:
    """保持原形态解析（str 进 str 出、list 进 list 出）——生图节点 image_val 直用。"""
    if value is None:
        return None
    if isinstance(value, list):
        return [resolve_consumable_image_url(item, prefer_remote=prefer_remote) for item in value]
    return resolve_consumable_image_url(value, prefer_remote=prefer_remote)


def _lookup_remote_url(storage_url: str) -> str | None:
    """按本地地址反查已镜像资产的云端直链（短会话；异常按未命中处理不阻断）。"""
    try:
        from sqlmodel import select

        from app.core.database import SessionLocal
        from app.modules.media.model.media import MediaAsset

        with SessionLocal() as session:
            statement = (
                select(MediaAsset)
                .where(
                    MediaAsset.storage_url == storage_url,
                    MediaAsset.delete_time == None,  # noqa: E711
                    MediaAsset.status == "success",
                    MediaAsset.remote_url != None,  # noqa: E711
                )
                .order_by(MediaAsset.created_at.desc())
                .limit(1)
            )
            asset = session.exec(statement).first()
            return asset.remote_url if asset else None
    except Exception:
        logger.warning("图片 remote_url 反查失败 storage_url=%s（按未命中处理）", storage_url, exc_info=True)
        return None


def _ingress_transit(storage_url: str) -> str | None:
    """经镜像存储做公共读临时中转（wf-temp/ 前缀）。不可用返回 None（非异常路径）。"""
    if not settings.MEDIA_MIRROR_ENABLED:
        return None
    if not (settings.MEDIA_MIRROR_BUCKET or settings.S3_BUCKET):
        return None
    try:
        from app.modules.media.service.mirror_service import MediaMirrorService

        content = _read_local_bytes(storage_url)
        return MediaMirrorService().upload_mirror_object(
            content,
            os.path.basename(storage_url),
            source_path=storage_url,
            prefix="wf-temp",
        )
    except Exception:
        logger.warning("图片 Ingress 中转失败 storage_url=%s（落情景 C）", storage_url, exc_info=True)
        return None


def _read_local_bytes(storage_url: str) -> bytes:
    from app.framework.storage import StorageService

    return StorageService.get_instance().read(storage_url)
