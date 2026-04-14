"""
字典模块服务
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery
from app.modules.base.model.auth import PageResult
from app.modules.dict.model.dict import (
    DictInfo,
    DictInfoCreateRequest,
    DictInfoRead,
    DictInfoUpdateRequest,
    DictType,
    DictTypeCreateRequest,
    DictTypeRead,
    DictTypeUpdateRequest,
)
from app.modules.base.service.admin_service import BaseAdminCrudService


class DictTypeService(BaseAdminCrudService):
    """字典类型服务"""

    def __init__(self, session: Session):
        super().__init__(session, DictType)

    def _before_add(self, data: dict) -> dict:
        key = data.get("key")
        duplicate = self.session.exec(select(DictType).where(DictType.key == key)).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字典标识已存在")
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        key = data.get("key")
        if key:
            duplicate = self.session.exec(
                select(DictType).where((DictType.id != entity.id) & (DictType.key == key))
            ).first()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字典标识已存在")
        return data


class DictInfoService(BaseAdminCrudService):
    """字典数据服务"""

    def __init__(self, session: Session):
        super().__init__(session, DictInfo)

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)
        data["typeId"] = data.get("type_id")
        data["parentId"] = data.get("parent_id")
        data["orderNum"] = data.get("order_num", 0)
        return data

    def _before_add(self, data: dict) -> dict:
        if "typeId" in data:
            data["type_id"] = data.pop("typeId")
        if "parentId" in data:
            data["parent_id"] = data.pop("parentId")
        if "orderNum" in data:
            data["order_num"] = data.pop("orderNum")
            
        self._ensure_type_exists(data.get("type_id"))
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        if "typeId" in data:
            data["type_id"] = data.pop("typeId")
        if "parentId" in data:
            data["parent_id"] = data.pop("parentId")
        if "orderNum" in data:
            data["order_num"] = data.pop("orderNum")
            
        self._ensure_type_exists(data.get("type_id"))
        return data

    def _ensure_type_exists(self, type_id: int | None) -> None:
        if type_id and self.session.get(DictType, type_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典类型不存在")

    def data(self, types: list[str]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        type_rows = list(self.session.exec(select(DictType).order_by(DictType.name.asc())).all())
        if types:
            type_rows = [item for item in type_rows if item.key in types]
        if not type_rows:
            return result
        type_map = {row.id: row for row in type_rows if row.id is not None}
        rows = list(
            self.session.exec(
                select(DictInfo)
                .where(DictInfo.type_id.in_(type_map.keys()))
                .order_by(DictInfo.order_num.asc(), DictInfo.created_at.asc())
            ).all()
        )
        for type_row in type_rows:
            result[type_row.key] = []
        for row in rows:
            type_row = type_map.get(row.type_id)
            if not type_row:
                continue
            result[type_row.key].append(
                {
                    "id": row.id,
                    "typeId": row.type_id,
                    "parentId": row.parent_id,
                    "name": row.name,
                    "label": row.name,
                    "value": _coerce_value(row.value),
                    "orderNum": row.order_num,
                }
            )
        return result

    def types(self) -> list[dict[str, Any]]:
        rows = list(self.session.exec(select(DictType).order_by(DictType.name.asc())).all())
        return [{"id": row.id, "key": row.key, "name": row.name} for row in rows]




def _coerce_value(value: str | None) -> Any:
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    return value
