"""工作流产物流转服务：workflow_output 自适应分类落地为产物实体。

执行成功终态时由 workflow_tasks 调用 persist_workflow_artifacts（best-effort，
失败仅告警不影响 success 终态）。产物与执行快照解耦——监控看过程，产物看结果。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.framework.storage import offload_payload
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

logger = logging.getLogger(__name__)

# 图片扩展名（忽略 query）：/uploads/ 前缀之外，只有明确图片后缀的 URL 才判 image，
# 防止网页/厂商签名直链（无扩展名）被误判
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


def is_image_url(value: str) -> bool:
    """URL 是否按图片产物处理：/uploads/ 前缀，或路径（忽略 query）为图片扩展名。"""
    if value.startswith("/uploads/"):
        return True
    if value.startswith(("http://", "https://")):
        path = urlsplit(value).path.lower()
        return any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS)
    return False


def classify_artifacts(workflow_output: Any) -> list[ArtifactDraft]:
    """把 end 节点的 workflow_output 自适应分类为产物清单（纯函数，不触库）。

    - dict：遍历顶层字段（结构化 output_fields 渲染结果）
    - str：文本模式输出，field_key 固定 "output"
    - list 全标量/URL → 逐项展开 field_path="key.idx"；含 dict/list 或 dict 值 → 整体 json
    - data:URL / None / 空串 / 数值 / 布尔 → 跳过
    """
    drafts: list[ArtifactDraft] = []
    if isinstance(workflow_output, str):
        _collect_scalar(workflow_output, "output", None, drafts)
        return drafts
    if not isinstance(workflow_output, dict):
        return drafts

    for key, value in workflow_output.items():
        field_key = str(key)[:150]
        if isinstance(value, dict):
            drafts.append(_json_draft(field_key, None, value))
        elif isinstance(value, list):
            if any(isinstance(item, (dict, list)) for item in value):
                drafts.append(_json_draft(field_key, None, value))
            else:
                for idx, item in enumerate(value):
                    _collect_scalar(item, field_key, f"{field_key}.{idx}", drafts)
        elif isinstance(value, (str, int, float, bool)):
            _collect_scalar(value, field_key, None, drafts)
    return drafts


def _collect_scalar(value: Any, field_key: str, field_path: str | None, drafts: list[ArtifactDraft]) -> None:
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
            for old in session.exec(
                select(WorkflowArtifact).where(WorkflowArtifact.instance_id == instance_id)
            ).all():
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
        logger.info(
            "工作流产物流转完成 instance=%d count=%d", instance_id, len(drafts)
        )
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
            select(MediaAsset).where(*base_where, MediaAsset.storage_url == draft.value).order_by(MediaAsset.created_at.desc())
        ).first()
        if asset is None:
            asset = session.exec(
                select(MediaAsset).where(*base_where, MediaAsset.original_url == draft.value).order_by(MediaAsset.created_at.desc())
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
