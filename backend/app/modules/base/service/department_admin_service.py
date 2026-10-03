"""
部门资源管理服务（由 admin_service.py 门面 re-export）。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.database import transaction
from app.modules.base.model.auth import (
    Department,
    DepartmentOrderItem,
    RoleDepartmentLink,
    User,
)
from app.modules.base.service.admin_base import BaseAdminCrudService, get_payload_attr
from app.modules.base.service.authority_service import clear_login_caches


class DepartmentAdminService(BaseAdminCrudService):
    """部门资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Department)

    def _before_add(self, data: dict) -> dict:
        data["is_active"] = True
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        return data

    def delete(self, ids: list[int], payload: Any = None, soft_delete: bool | None = None) -> dict:
        if not ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少待删除的部门 ID")
        delete_user = bool(get_payload_attr(payload, "delete_user", False)) if payload else False
        department_ids = self._collect_descendant_department_ids(ids)
        root_ids = set(ids)
        users_to_clear_cache: list[int] = []

        with transaction(self.session):
            for department_id in sorted(department_ids, reverse=True):
                department = self.session.get(Department, department_id)
                if not department:
                    continue
                if not delete_user:
                    fallback_department_id = department.parent_id
                    if department_id in root_ids and fallback_department_id is not None:
                        for user in list(
                            self.session.exec(select(User).where(User.department_id == department_id)).all()
                        ):
                            user.department_id = fallback_department_id
                            self.session.add(user)
                else:
                    for user in list(self.session.exec(select(User).where(User.department_id == department_id)).all()):
                        users_to_clear_cache.append(user.id)
                        self.session.delete(user)
                for link in list(
                    self.session.exec(
                        select(RoleDepartmentLink).where(RoleDepartmentLink.department_id == department_id)
                    ).all()
                ):
                    self.session.delete(link)
                self.session.delete(department)

        # 事务成功后清理外部用户缓存
        for uid in users_to_clear_cache:
            clear_login_caches(uid)

        return {"success": True, "deleted_ids": department_ids}

    def order(self, payload: list[dict] | list[DepartmentOrderItem]) -> dict:
        with transaction(self.session):
            for item in payload:
                data = item if isinstance(item, DepartmentOrderItem) else DepartmentOrderItem(**item)
                department = self.session.get(Department, data.id)
                if not department:
                    continue
                department.parent_id = data.parent_id
                department.sort_order = data.sort_order
                self.session.add(department)
        return {"success": True}

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)

        # 补充 parent_name
        if data.get("parent_id"):
            parent = self.session.get(Department, data["parent_id"])
            if parent:
                data["parent_name"] = parent.name
        return data
