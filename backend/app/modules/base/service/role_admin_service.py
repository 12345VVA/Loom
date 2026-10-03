"""
角色资源管理服务（由 admin_service.py 门面 re-export）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.database import transaction
from app.modules.base.model.auth import (
    Department,
    Menu,
    Role,
    RoleDepartmentLink,
    RoleMenuAssignRequest,
    RoleMenuLink,
    UserRoleLink,
)
from app.modules.base.service.admin_base import (
    BaseAdminCrudService,
    get_payload_attr,
    get_request_ip_from_payload,
    has_payload_attr,
)
from app.modules.base.service.authority_service import (
    clear_login_caches_for_roles,
    clear_login_caches_for_users,
)

logger = logging.getLogger(__name__)


class RoleAdminService(BaseAdminCrudService):
    """角色资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Role)

    def _after_add(self, entity: Role, payload: Any) -> None:
        """角色创建后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            SysSecurityLogService(self.session).create_entry(
                operator_id=operator_id or 0,
                operator_name=operator_name,
                operator_ip=operator_ip,
                target_type="role",
                target_id=entity.id,
                target_name=entity.name,
                operation="create",
                module="role",
                resource_path=f"/admin/base/sys/role/{entity.id}",
                new_value=json.dumps(
                    {"name": entity.name, "code": entity.code, "data_scope": entity.data_scope}, ensure_ascii=False
                ),
                business_type="role_management",
                status=1,
                remark="创建新角色",
            )
        except Exception as exc:
            logger.warning(f"记录角色创建审计日志失败 - role_id: {entity.id}", exc_info=exc)

        menu_ids = get_payload_attr(payload, "menu_ids")
        if menu_ids is not None:
            self._replace_role_menus(entity.id, menu_ids)
        department_ids = get_payload_attr(payload, "department_ids")
        if department_ids is not None:
            self._replace_role_departments(entity.id, department_ids)

    def _after_update(self, entity: Role, payload: Any) -> None:
        """角色更新后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = get_payload_attr(payload, "_operator_id") or get_payload_attr(payload, "current_user_id")
            operator_name = get_payload_attr(payload, "_operator_name") or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 检查权限调整操作
            sensitive_operations = []
            if has_payload_attr(payload, "menu_ids"):
                sensitive_operations.append("update_permissions")
            if has_payload_attr(payload, "department_ids"):
                sensitive_operations.append("update_data_scope")
            if has_payload_attr(payload, "data_scope"):
                sensitive_operations.append("update_data_scope")

            if sensitive_operations:
                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id or 0,
                    operator_name=operator_name,
                    operator_ip=operator_ip,
                    target_type="role",
                    target_id=entity.id,
                    target_name=entity.name,
                    operation="update",
                    module="role",
                    resource_path=f"/admin/base/sys/role/{entity.id}",
                    business_type="role_management",
                    status=1,
                    remark=f"调整角色权限: {', '.join(sensitive_operations)}",
                )
        except Exception as exc:
            logger.warning(f"记录角色更新审计日志失败 - role_id: {entity.id}", exc_info=exc)

        menu_ids = get_payload_attr(payload, "menu_ids")
        if menu_ids is not None:
            self._replace_role_menus(entity.id, menu_ids)
        department_ids = get_payload_attr(payload, "department_ids")
        if department_ids is not None:
            self._replace_role_departments(entity.id, department_ids)
        clear_login_caches_for_roles(self.session, [entity.id])
        self._clear_role_related_caches([entity.id])

    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        """角色删除后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = get_payload_attr(payload, "_operator_id") or get_payload_attr(payload, "current_user_id") or 0
            operator_name = get_payload_attr(payload, "_operator_name") or "system"

            for role_id in ids:
                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id,
                    operator_name=operator_name,
                    operator_ip=None,
                    target_type="role",
                    target_id=role_id,
                    target_name=str(role_id),
                    operation="delete",
                    module="role",
                    resource_path=f"/admin/base/sys/role/{role_id}",
                    business_type="role_management",
                    status=1,
                    remark="删除角色",
                )
        except Exception as exc:
            logger.warning(f"记录角色删除审计日志失败 - role_ids: {ids}", exc_info=exc)

        clear_login_caches_for_roles(self.session, ids)
        self._after_delete_cache(ids)

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)
        # 补充关联列表
        data["menu_ids"] = [
            link.menu_id for link in self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == row.id)).all()
        ]
        data["department_ids"] = [
            link.department_id
            for link in self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == row.id)).all()
        ]
        return data

    def _before_add(self, data: dict) -> dict:
        label = data.get("label")
        code = data.get("code") or label
        existing = self.session.exec(select(Role).where((Role.code == code) | (Role.label == label))).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")

        data["code"] = code
        data["data_scope"] = "department" if data.get("department_ids") else "self"
        return data

    def _before_update(self, data: dict, entity: Role) -> dict:
        label = data.get("label") or entity.label
        code = data.get("code") or data.get("label") or entity.code

        duplicate = self.session.exec(
            select(Role).where((Role.id != entity.id) & ((Role.code == code) | (Role.label == label)))
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")

        if "department_ids" in data:
            data["data_scope"] = "department" if data["department_ids"] else "self"
        return data

    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
        roles = list(self.session.exec(select(Role).where(Role.id.in_(ids))).all())
        if any(role.code == "admin" for role in roles):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除系统管理员角色")

        # 收集受影响的用户 ID 以便后续清理缓存
        affected_user_ids = [
            link.user_id for link in self.session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(ids))).all()
        ]
        self._affected_user_ids_storage = affected_user_ids  # 临时存储
        return ids

    def _after_delete_cache(self, ids: list[int]) -> None:
        if hasattr(self, "_affected_user_ids_storage"):
            clear_login_caches_for_users(self._affected_user_ids_storage)
            del self._affected_user_ids_storage

    def assign_menus(self, payload: RoleMenuAssignRequest) -> dict:
        role = self.session.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        with transaction(self.session):
            self._replace_role_menus(payload.role_id, payload.menu_ids)
        self._clear_role_related_caches([payload.role_id])
        return {"success": True, "role_id": payload.role_id, "menu_ids": payload.menu_ids}

    def _replace_role_menus(self, role_id: int, menu_ids: list[int]) -> None:
        for link in list(self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role_id)).all()):
            self.session.delete(link)
        if menu_ids:
            menus = list(self.session.exec(select(Menu).where(Menu.id.in_(menu_ids))).all())
            found_menu_ids = {menu.id for menu in menus if menu.id is not None}
            missing_ids = sorted(set(menu_ids) - found_menu_ids)
            if missing_ids:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"菜单不存在: {missing_ids}")
            for menu_id in menu_ids:
                self.session.add(RoleMenuLink(role_id=role_id, menu_id=menu_id))
        self.session.flush()

    def _replace_role_departments(self, role_id: int, department_ids: list[int]) -> None:
        for link in list(
            self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == role_id)).all()
        ):
            self.session.delete(link)
        if department_ids:
            departments = list(self.session.exec(select(Department).where(Department.id.in_(department_ids))).all())
            found_ids = {item.id for item in departments if item.id is not None}
            missing_ids = sorted(set(department_ids) - found_ids)
            if missing_ids:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"部门不存在: {missing_ids}")
            for department_id in department_ids:
                self.session.add(RoleDepartmentLink(role_id=role_id, department_id=department_id))
        self.session.flush()

    def _clear_role_related_caches(self, role_ids: list[int]) -> None:
        clear_login_caches_for_roles(self.session, role_ids)
