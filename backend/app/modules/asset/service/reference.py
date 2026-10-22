"""参考图集共享逻辑（三表复用）：JSON 契约解析 / 增删重排。

ref_image_ids JSON 契约（决策 #28）：[{"id": <mediaId>, "role"?: "primary"}]；
兼容纯 id 数组与无 role 成员（按位置语义：首位天然 primary）。

注意：本模块顶部的纯函数是被 service.base.py 引用的叶子（无模块依赖），
AssetCrudServiceBase 仅经 TYPE_CHECKING 引用，勿在顶层 import 形成循环。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from app.modules.asset.model.asset import MAX_REF_IMAGES, REFERENCE_ROLES_CORE

if TYPE_CHECKING:
    from app.modules.asset.service.base import AssetCrudServiceBase


def parse_ref_entries(raw: str | None) -> list[dict]:
    """ref_image_ids JSON → [{id:int, role?:str}]；容错解析（坏数据按空处理不炸消费链）。"""
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(loaded, list):
        return []

    entries: list[dict] = []
    for item in loaded:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            entry: dict[str, Any] = {"id": item["id"]}
            if isinstance(item.get("role"), str) and item["role"]:
                entry["role"] = item["role"]
            entries.append(entry)
        elif isinstance(item, int):
            # 旧数据纯 id 形态（按位置语义，首位视作 primary）
            entries.append({"id": item})
    return entries


def order_entries_by_role(entries: list[dict]) -> list[dict]:
    """primary 固定第一顺位，其余按列表顺序补足（决策 #28；无标记首位视作 primary）。"""
    if not entries:
        return []
    has_primary = any(entry.get("role") == "primary" for entry in entries)
    if not has_primary:
        return list(entries)
    primary = [entry for entry in entries if entry.get("role") == "primary"]
    rest = [entry for entry in entries if entry.get("role") != "primary"]
    return primary + rest


def normalize_entry_ids(entries: list[dict]) -> list[int]:
    """按 role 语义排序后的 media id 列表（注入/预览消费形态）。"""
    return [entry["id"] for entry in order_entries_by_role(entries)]


class ReferenceService:
    """参考图集写操作（三表复用）；写权限 = 编辑权限（archived 期间锁死）。"""

    def __init__(self, session, service: AssetCrudServiceBase):
        self.session = session
        self.service = service

    def add_reference(self, asset_id: int, media_id: int, role: str | None, current_user) -> dict:

        from app.modules.media.model.media import MediaAsset

        entity = self._get_editable(asset_id, current_user)
        if role is not None and role not in REFERENCE_ROLES_CORE:
            raise HTTPException(status_code=400, detail=f"参考图 role 仅支持 {sorted(REFERENCE_ROLES_CORE)}")

        media = self.session.get(MediaAsset, media_id)
        if media is None or media.delete_time is not None:
            raise HTTPException(status_code=404, detail="媒体资产不存在或已删除")

        entries = parse_ref_entries(entity.ref_image_ids)
        # MD5 防重复入库（需求 4.3）：同 md5 已在集中则幂等返回现状
        if media.md5:
            md5_by_id = self._md5_map([entry["id"] for entry in entries])
            if md5_by_id.get(media.md5):
                return self._payload(entity, parse_ref_entries(entity.ref_image_ids), [])

        if len(entries) >= MAX_REF_IMAGES:
            raise HTTPException(status_code=400, detail=f"参考图数量已达上限（{MAX_REF_IMAGES} 张）")

        entry: dict[str, Any] = {"id": media_id}
        if role:
            entry["role"] = role
        entries.append(entry)
        entity.ref_image_ids = json.dumps(entries, ensure_ascii=False)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return self._payload(
            entity,
            entries,
            self.service._media_map_for([{"id": entity.id, "ref_image_ids": entity.ref_image_ids}])
            .get(entity.id, {})
            .get("missing", []),
        )

    def remove_reference(self, asset_id: int, media_id: int, current_user) -> dict:
        entity = self._get_editable(asset_id, current_user)
        entries = [entry for entry in parse_ref_entries(entity.ref_image_ids) if entry["id"] != media_id]
        entity.ref_image_ids = json.dumps(entries, ensure_ascii=False)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return self._payload(entity, entries, [])

    def reorder_references(self, asset_id: int, media_ids: list[int], current_user) -> dict:
        entity = self._get_editable(asset_id, current_user)
        entries = parse_ref_entries(entity.ref_image_ids)
        by_id = {entry["id"]: entry for entry in entries}
        unknown = [mid for mid in media_ids if mid not in by_id]
        if unknown:
            raise HTTPException(status_code=400, detail=f"参考图列表包含未关联的媒体 id：{unknown}")
        if sorted(media_ids) != sorted(by_id.keys()):
            raise HTTPException(status_code=400, detail="重排列表必须包含全部参考图，不允许增删")
        ordered = [by_id[mid] for mid in media_ids]
        entity.ref_image_ids = json.dumps(ordered, ensure_ascii=False)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return self._payload(entity, ordered, [])

    # --- 内部 ---

    def _get_editable(self, asset_id: int, current_user):
        entity = self.session.get(self.service.model, asset_id)
        if entity is None or entity.delete_time is not None:
            raise HTTPException(status_code=404, detail="资产不存在")
        self.service._assert_editable(entity, current_user)
        return entity

    def _md5_map(self, media_ids: list[int]) -> dict[str, int]:
        from sqlmodel import select

        from app.modules.media.model.media import MediaAsset

        if not media_ids:
            return {}
        rows = self.session.exec(
            select(MediaAsset.id, MediaAsset.md5).where(
                MediaAsset.id.in_(media_ids),
                MediaAsset.md5 != None,  # noqa: E711
            )
        ).all()
        return {md5: mid for mid, md5 in rows}

    @staticmethod
    def _payload(entity, entries: list[dict], missing: list[int]) -> dict:
        return {
            "id": entity.id,
            "referenceImages": entries,
            "missingMediaIds": missing,
        }
