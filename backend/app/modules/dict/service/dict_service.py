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

    def list(self, query: CrudQuery | None = None) -> list[DictTypeRead]:
        statement = select(DictType)
        statement = self._apply_query(statement, DictType, query, fallback_field="created_at")
        rows = list(self.session.exec(statement).all())
        return [self._build_read(row) for row in rows]

    def page(self, query: CrudQuery) -> PageResult[DictTypeRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(DictType)
        statement = self._apply_query(statement, DictType, query, fallback_field="created_at")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_read(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> DictTypeRead:
        row = self.session.get(DictType, id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典类型不存在")
        return self._build_read(row)

    def add(self, payload: DictTypeCreateRequest) -> DictTypeRead:
        duplicate = self.session.exec(select(DictType).where(DictType.key == payload.key)).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字典标识已存在")
        row = DictType(name=payload.name, key=payload.key, updated_at=datetime.utcnow())
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def update(self, payload: DictTypeUpdateRequest) -> DictTypeRead:
        row = self.session.get(DictType, payload.id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典类型不存在")
        duplicate = self.session.exec(select(DictType).where((DictType.id != payload.id) & (DictType.key == payload.key))).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字典标识已存在")
        row.name = payload.name
        row.key = payload.key
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def delete(self, ids: list[int]) -> dict[str, Any]:
        if not ids:
            return {"success": True, "deleted_ids": []}
        for row in list(self.session.exec(select(DictInfo).where(DictInfo.type_id.in_(ids))).all()):
            self.session.delete(row)
        for row in list(self.session.exec(select(DictType).where(DictType.id.in_(ids))).all()):
            self.session.delete(row)
        self.session.commit()
        return {"success": True, "deleted_ids": ids}

    @staticmethod
    def _build_read(row: DictType) -> DictTypeRead:
        return DictTypeRead(
            id=row.id,
            name=row.name,
            key=row.key,
            createTime=row.created_at,
            updateTime=row.updated_at or row.created_at,
        )


class DictInfoService(BaseAdminCrudService):
    """字典数据服务"""

    def __init__(self, session: Session):
        super().__init__(session, DictInfo)

    def list(self, query: CrudQuery | None = None) -> list[DictInfoRead]:
        statement = select(DictInfo)
        statement = self._apply_query(statement, DictInfo, query, fallback_field="created_at")
        rows = list(self.session.exec(statement).all())
        return [self._build_read(row) for row in rows]

    def page(self, query: CrudQuery) -> PageResult[DictInfoRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(DictInfo)
        statement = self._apply_query(statement, DictInfo, query, fallback_field="created_at")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_read(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> DictInfoRead:
        row = self.session.get(DictInfo, id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典数据不存在")
        return self._build_read(row)

    def add(self, payload: DictInfoCreateRequest) -> DictInfoRead:
        self._ensure_type_exists(payload.typeId)
        row = DictInfo(
            type_id=payload.typeId,
            parent_id=payload.parentId,
            name=payload.name,
            value=payload.value or "",
            order_num=payload.orderNum,
            remark=payload.remark,
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def update(self, payload: DictInfoUpdateRequest) -> DictInfoRead:
        row = self.session.get(DictInfo, payload.id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典数据不存在")
        self._ensure_type_exists(payload.typeId)
        row.type_id = payload.typeId
        row.parent_id = payload.parentId
        row.name = payload.name
        row.value = payload.value or ""
        row.order_num = payload.orderNum
        row.remark = payload.remark
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def delete(self, ids: list[int]) -> dict[str, Any]:
        if not ids:
            return {"success": True, "deleted_ids": []}
        delete_ids = set(ids)
        for item_id in ids:
            delete_ids.update(self._collect_descendant_ids(item_id))
        for row in list(self.session.exec(select(DictInfo).where(DictInfo.id.in_(sorted(delete_ids)))).all()):
            self.session.delete(row)
        self.session.commit()
        return {"success": True, "deleted_ids": sorted(delete_ids)}

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

    @staticmethod
    def _build_read(row: DictInfo) -> DictInfoRead:
        return DictInfoRead(
            id=row.id,
            typeId=row.type_id,
            parentId=row.parent_id,
            name=row.name,
            value=row.value,
            orderNum=row.order_num,
            remark=row.remark,
            createTime=row.created_at,
            updateTime=row.updated_at or row.created_at,
        )

    def _ensure_type_exists(self, type_id: int) -> None:
        if self.session.get(DictType, type_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典类型不存在")

    def _collect_descendant_ids(self, root_id: int) -> list[int]:
        rows = list(self.session.exec(select(DictInfo)).all())
        children_map: dict[int | None, list[int]] = {}
        for row in rows:
            children_map.setdefault(row.parent_id, []).append(row.id)
        result: set[int] = set()
        stack = [root_id]
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            stack.extend(children_map.get(current, []))
        return sorted(result)


def _coerce_value(value: str | None) -> Any:
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    return value
