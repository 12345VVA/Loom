"""工作流产物流转服务：workflow_output 自适应分类落地为产物实体。

执行成功终态时由 workflow_tasks 调用 persist_workflow_artifacts（best-effort，
失败仅告警不影响 success 终态）。产物与执行快照解耦——监控看过程，产物看结果。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.framework.storage import offload_payload
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

logger = logging.getLogger(__name__)

# 图片扩展名（忽略 query）：/uploads/ 前缀之外的主判定依据
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".avif"}
_MAX_TEXT_LEN = 2_000_000  # 单条文本产物入库上限（超长截断，防异常输出撑爆存储）


@dataclass
class ArtifactDraft:
    """单条产物的落库前描述（未关联 session）。"""

    field_key: str
    field_path: str | None
    asset_type: str  # image | text | json
    value: str  # 原始值（image 为 URL；text/json 为文本内容）
    media_asset_id: int | None = None
    storage_url: str | None = None


# 常见受限对象存储域（签名直链常无扩展名且不配 CORS）。域级匹配防子串误伤（如 macos.dev 含 "cos."）
_RESTRICTED_HOST_SUFFIXES = ("volces.com", "aliyuncs.com", "myqcloud.com", "amazonaws.com", "blob.core.windows.net")


def is_internal_var_key(key: str) -> bool:
    """是否工作流内部通道变量（如 {output}__src 厂商临时 URL，专供下游节点 imageVariable
    引用，见 workflow_service.execute_image_generator_node）：非交付产物，不参与分类。"""
    return str(key).endswith("__src")


def _is_restricted_storage_host(host: str) -> bool:
    """是否常见对象存储域：tos-/oss- 子域前缀，或域级后缀匹配。"""
    if host.startswith(("tos-", "oss-")):
        return True
    return any(host == suffix or host.endswith("." + suffix) for suffix in _RESTRICTED_HOST_SUFFIXES)


def is_image_url(value: str) -> bool:
    """URL 是否按图片产物处理：/uploads/ 前缀、图片扩展名，或受限对象存储的无扩展名签名直链。

    有扩展名时仅按扩展名判定（存储桶上的 .mp3/.pdf 直链不误判为图片）；
    host 启发式仅在路径无扩展名时兜底（生图转存失败回退厂商临时 URL 的场景）。
    """
    if not isinstance(value, str):
        return False
    val = value.strip()
    if not val or " " in val or "\n" in val:
        return False
    if val.startswith("/uploads/"):
        return True
    if val.startswith(("http://", "https://")):
        parts = urlsplit(val)
        path = parts.path.lower()
        if any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS):
            return True
        if os.path.splitext(path)[1]:
            # 有扩展名但非图片：不再看 host，防止对象存储域上的音频/文档直链被误判
            return False
        return _is_restricted_storage_host((parts.hostname or "").lower())
    return False


def classify_artifacts(workflow_output: Any) -> list[ArtifactDraft]:
    """把 end 节点的 workflow_output 自适应分类为产物清单（纯函数，不触库）。

    - dict：遍历顶层字段（结构化 output_fields 渲染结果，若含图片字段展开为 image 产物）
    - str：文本模式输出，field_key 固定 "output"
    - list 全标量/URL → 逐项展开 field_path="key.idx"；
      若为包含图片字段的对象数组（如循环节点内页输出）→ 提取每张图片为独立 image 产物，
      且 json 整体与图片并存（失败迭代的 error、文案等非图片数据不丢失）
    - __src 结尾的内部通道变量不分类（厂商临时 URL 非交付产物）
    - image 全程按 URL 去重：循环快照会重复携带外层作用域图片（如封面进每个迭代 dict），
      同一 URL 只保留首见 field_path（多个交付字段指向同一 URL 时牺牲后续溯源）
    - data:URL / None / 空串 / 数值 / 布尔 → 跳过
    """
    drafts: list[ArtifactDraft] = []
    seen_image_urls: set[str] = set()

    def add_image(draft: ArtifactDraft) -> None:
        if draft.value in seen_image_urls:
            return
        seen_image_urls.add(draft.value)
        drafts.append(draft)

    if isinstance(workflow_output, str):
        _collect_scalar(workflow_output, "output", None, drafts, seen_image_urls)
        return drafts
    if not isinstance(workflow_output, dict):
        return drafts

    for key, value in workflow_output.items():
        if is_internal_var_key(key):
            continue
        field_key = str(key)[:150]
        if isinstance(value, dict):
            has_sub_images = False
            for sub_k, sub_v in value.items():
                if is_internal_var_key(sub_k):
                    continue
                if isinstance(sub_v, str) and is_image_url(sub_v):
                    add_image(ArtifactDraft(field_key, f"{field_key}.{sub_k}", "image", sub_v))
                    has_sub_images = True
            if not has_sub_images:
                drafts.append(_json_draft(field_key, None, value))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    for sub_k, sub_v in item.items():
                        if is_internal_var_key(sub_k):
                            continue
                        if isinstance(sub_v, str) and is_image_url(sub_v):
                            add_image(ArtifactDraft(field_key, f"{field_key}.{idx}.{sub_k}", "image", sub_v))
                elif isinstance(item, (str, int, float, bool)):
                    _collect_scalar(item, field_key, f"{field_key}.{idx}", drafts, seen_image_urls)
            # 图片提取与 json 整体并存：循环快照里的 error/文案不随图片提取丢失
            if any(isinstance(item, (dict, list)) for item in value):
                drafts.append(_json_draft(field_key, None, value))
        elif isinstance(value, (str, int, float, bool)):
            _collect_scalar(value, field_key, None, drafts, seen_image_urls)
    return drafts


def _collect_scalar(
    value: Any,
    field_key: str,
    field_path: str | None,
    drafts: list[ArtifactDraft],
    seen_image_urls: set[str] | None = None,
) -> None:
    """标量值的分类与跳过规则。"""
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    if text.startswith("data:"):
        # 内联 base64 会撑爆 content 列，不入库
        logger.debug("产物字段含 data:URL，跳过 field=%s/%s", field_key, field_path)
        return
    if len(text) > _MAX_TEXT_LEN:
        text = text[:_MAX_TEXT_LEN]
    if is_image_url(text):
        if seen_image_urls is not None:
            if text in seen_image_urls:
                return
            seen_image_urls.add(text)
        drafts.append(ArtifactDraft(field_key, field_path, "image", text))
    else:
        drafts.append(ArtifactDraft(field_key, field_path, "text", text))


def _json_draft(field_key: str, field_path: str | None, value: Any) -> ArtifactDraft:
    content = json.dumps(value, ensure_ascii=False, default=str)
    return ArtifactDraft(field_key, field_path, "json", content[:_MAX_TEXT_LEN])


def persist_workflow_artifacts(
    instance_id: int,
    definition_id: int,
    version_id: int | None,
    user_id: int | None,
    node_hint: str | None,
    workflow_output: Any,
    *,
    engine=None,
) -> None:
    """把 workflow_output 落地为产物实体（best-effort：失败仅告警，不影响 success 终态）。

    幂等：先硬删该实例旧产物再插（success 为终态、celery max_retries=0，实际重放概率趋零）。
    """
    from app.core.database import engine as default_engine

    engine = engine or default_engine
    drafts = classify_artifacts(workflow_output)
    if not drafts:
        return
    try:
        stale_refs: list[str] = []
        with Session(engine) as session:
            for old in session.exec(select(WorkflowArtifact).where(WorkflowArtifact.instance_id == instance_id)).all():
                if old.content_ref:
                    stale_refs.append(old.content_ref)
                session.delete(old)
            for draft in drafts:
                session.add(_build_row(instance_id, definition_id, version_id, user_id, node_hint, draft, session))
            session.commit()
        # commit 成功后再删旧载荷文件（新 ref 是新 uuid 不会误删；失败残留由孤儿清理兜底）
        for ref in stale_refs:
            try:
                from app.framework.storage import StorageService

                StorageService.get_instance().delete(ref)
            except Exception:
                logger.warning("旧产物载荷文件删除失败 ref=%s", ref, exc_info=True)
        logger.info("工作流产物流转完成 instance=%d count=%d", instance_id, len(drafts))
    except Exception:
        logger.warning("工作流产物流转失败 instance=%d", instance_id, exc_info=True)


def _build_row(
    instance_id: int,
    definition_id: int,
    version_id: int | None,
    user_id: int | None,
    node_hint: str | None,
    draft: ArtifactDraft,
    session: Session,
) -> WorkflowArtifact:
    media_asset_id: int | None = None
    storage_url: str | None = None
    original_url: str | None = None
    content: str | None = None
    content_ref: str | None = None

    if draft.asset_type == "image":
        original_url = draft.value
        from app.modules.media.model.media import MediaAsset

        base_where = (MediaAsset.delete_time == None, MediaAsset.status == "success")  # noqa: E711
        # 优先按永久地址命中；未命中再按厂商原始 URL（同图去重复用场景）
        asset = session.exec(
            select(MediaAsset)
            .where(*base_where, MediaAsset.storage_url == draft.value)
            .order_by(MediaAsset.created_at.desc())
        ).first()
        if asset is None:
            asset = session.exec(
                select(MediaAsset)
                .where(*base_where, MediaAsset.original_url == draft.value)
                .order_by(MediaAsset.created_at.desc())
            ).first()
        if asset is not None and asset.storage_url:
            media_asset_id = asset.id
            storage_url = asset.storage_url
        else:
            # 未命中已转存资产（如转存失败回退的临时 URL）：仅记录原始 URL 供溯源
            storage_url = draft.value if draft.value.startswith("/uploads/") else None
    else:
        inline, ref = offload_payload(draft.value)
        content = inline or None
        content_ref = ref

    return WorkflowArtifact(
        instance_id=instance_id,
        definition_id=definition_id,
        version_id=version_id,
        node_id=node_hint,
        user_id=user_id,
        field_key=draft.field_key,
        field_path=draft.field_path,
        asset_type=draft.asset_type,
        media_asset_id=media_asset_id,
        storage_url=storage_url,
        original_url=original_url,
        content=content,
        content_ref=content_ref,
    )
