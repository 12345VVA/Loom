"""资产三表共享 CRUD 服务基类：可见性过滤 / 状态机保护 / 编辑权限 / 悬空标注。

权限矩阵与状态机口径见设计文档 3.3（docs/02-业务模块/IP资产库模块设计-2026-10-22.md）：
- 管理面查看：draft 仅创建者（管理员可见全量）；published/archived 全员；
- 编辑：draft/published 仅创建者（管理员对他人 draft 只读）；archived 无人可编辑；
- 软删 / 状态迁移：创建者 + 管理员；
- 管理员判定：User.is_super_admin（框架现成字段，与 assert_run_owned 同源口径）。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_PUBLISHED,
    ASSET_STATUS_TRANSITIONS,
)
from app.modules.asset.service.reference import parse_ref_entries
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService


def _is_super_admin(current_user: User | None) -> bool:
    """防各调用形态缺字段，与 workflow_eval.assert_run_owned 同款防御取值。"""
    return bool(current_user is not None and getattr(current_user, "is_super_admin", False))


class AssetCrudServiceBase(BaseAdminCrudService):
    """asset 三表共享逻辑；子类只需注入模型类。"""

    def __init__(self, session: Session, model: type):
        super().__init__(session, model)

    # --- CRUD 生命周期（标准动作由框架注入 current_user）---

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增：强制 draft + 创建者；Create DTO 本就不含 status/created_by，此处为服务端兜底。"""
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)
        data.pop("created_by", None)
        data["status"] = ASSET_STATUS_DRAFT
        if current_user is not None:
            data["created_by"] = current_user.id
        self._assert_code_available(data.get("code"))
        return super().add(data)

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新：编辑权限 + archived 锁 + 状态字段剔除 + code 唯一性。"""
        id_val = payload.get("id") if isinstance(payload, dict) else getattr(payload, "id", None)
        entity = self.session.get(self.model, id_val) if id_val is not None else None
        if entity is None:
            return super().update(payload)  # 404 由基类统一给出
        self._assert_editable(entity, current_user)

        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)  # 双保险：状态只经 transition_status 迁移
        if "code" in data:
            self._assert_code_available(data.get("code"), exclude_id=id_val)
        return super().update(data)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """软删：创建者 + 管理员（任意状态，权限矩阵「软删」行）。"""
        if current_user is not None and ids:
            for entity in self.session.exec(select(self.model).where(self.model.id.in_(ids))).all():
                if not _is_super_admin(current_user) and entity.created_by != current_user.id:
                    raise HTTPException(status_code=403, detail="仅创建者或管理员可删除该资产")
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    # --- 可见性过滤（info/list/page 三入口共用，叠加在软删与 DataScope 之后）---

    def _apply_query(self, statement, model, query, current_user=None, **kwargs):
        statement = super()._apply_query(statement, model, query, current_user, **kwargs)
        if current_user is not None and not _is_super_admin(current_user):
            statement = statement.where(or_(model.status != ASSET_STATUS_DRAFT, model.created_by == current_user.id))
        return statement

    # --- 出口增强：参考图悬空标注（missingMediaIds，详情页失效标注数据源）---

    def _finalize_data(self, data: Any) -> Any:
        if isinstance(data, list):
            missing_map = self._missing_map_for([item for item in data if isinstance(item, dict)])
            for item in data:
                if isinstance(item, dict):
                    item["missing_media_ids"] = missing_map.get(item.get("id"), [])
        elif isinstance(data, dict):
            missing_map = self._missing_map_for([data])
            data["missing_media_ids"] = missing_map.get(data.get("id"), [])
        return super()._finalize_data(data)

    def _missing_map_for(self, rows: list[dict]) -> dict[int, list[int]]:
        """一次 IN 查询解析多行参考图的悬空 media id（避免页内 N+1）。"""
        from app.modules.media.model.media import MediaAsset

        row_ids: dict[int, list[int]] = {}
        wanted: set[int] = set()
        for row in rows:
            asset_id = row.get("id")
            if asset_id is None:
                continue
            entry_ids = [entry.get("id") for entry in parse_ref_entries(row.get("ref_image_ids"))]
            entry_ids = [mid for mid in entry_ids if isinstance(mid, int)]
            row_ids[asset_id] = entry_ids
            wanted.update(entry_ids)
        if not wanted:
            return {}

        available = set(
            self.session.exec(
                select(MediaAsset.id).where(
                    MediaAsset.id.in_(list(wanted)),
                    MediaAsset.delete_time == None,  # noqa: E711
                )
            ).all()
        )
        return {asset_id: [mid for mid in ids if mid not in available] for asset_id, ids in row_ids.items() if ids}

    # --- 状态机（设计 3.3：独立迁移方法，不经 _before_update 的状态剔除）---

    def transition_status(self, asset_id: int, target: str, current_user: User | None = None) -> Any:
        """publish/archive/restore 共用迁移：创建者+管理员；非法迁移 400。"""
        entity = self.session.get(self.model, asset_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="资产不存在")
        self._assert_manager(entity, current_user, action="迁移该资产状态")
        allowed = ASSET_STATUS_TRANSITIONS.get(entity.status, set())
        if target not in allowed:
            raise HTTPException(status_code=400, detail=f"非法状态迁移：{entity.status} → {target}")
        entity.status = target
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    # --- 权限断言 ---

    def _assert_editable(self, entity: Any, current_user: User | None) -> None:
        """编辑权限（矩阵「编辑」行）：archived 锁死；draft 仅创建者；published 创建者+管理员。"""
        if current_user is None:
            raise HTTPException(status_code=401, detail="未登录")
        if entity.status == ASSET_STATUS_ARCHIVED:
            raise HTTPException(status_code=403, detail="资产已归档，请先恢复再编辑")
        if entity.created_by == current_user.id:
            return
        if _is_super_admin(current_user) and entity.status == ASSET_STATUS_PUBLISHED:
            return
        if entity.status == ASSET_STATUS_DRAFT:
            raise HTTPException(status_code=403, detail="他人草稿为只读，仅创建者可编辑")
        raise HTTPException(status_code=403, detail="仅创建者或管理员可编辑该资产")

    def _assert_manager(self, entity: Any, current_user: User | None, *, action: str) -> None:
        """管理面操作（状态迁移/软删）：创建者 + 管理员。"""
        if current_user is None:
            raise HTTPException(status_code=401, detail="未登录")
        if entity.created_by != current_user.id and not _is_super_admin(current_user):
            raise HTTPException(status_code=403, detail=f"仅创建者或管理员可{action}")

    def _assert_code_available(self, code: Any, exclude_id: int | None = None) -> None:
        """code 唯一性（应用层友好 400；partial unique 索引兜底并发）。"""
        if not code:
            return
        statement = select(self.model).where(
            self.model.code == code,
            self.model.delete_time == None,  # noqa: E711
        )
        if exclude_id is not None:
            statement = statement.where(self.model.id != exclude_id)
        if self.session.exec(statement).first() is not None:
            raise HTTPException(status_code=400, detail=f"标识「{code}」已存在")
