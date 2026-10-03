"""
用户资源管理服务（由 admin_service.py 门面 re-export）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.database import transaction
from app.core.security import add_user_all_tokens_to_blacklist, hash_password, validate_password_strength
from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.base.model.auth import (
    Department,
    Role,
    User,
    UserListItem,
    UserMoveRequest,
    UserRoleAssignRequest,
    UserRoleLink,
)
from app.modules.base.service.admin_base import (
    BaseAdminCrudService,
    get_payload_attr,
    get_request_ip_from_payload,
)
from app.modules.base.service.authority_service import (
    clear_login_caches,
    clear_login_caches_for_users,
    get_user_roles,
)

logger = logging.getLogger(__name__)


class UserAdminService(BaseAdminCrudService):
    """用户资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, User)

    def _after_add(self, entity: User, payload: Any) -> None:
        """用户创建后记录安全审计日志并绑定角色"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            # 获取当前操作者信息
            operator_id = get_payload_attr(payload, "_operator_id") or get_payload_attr(payload, "current_user_id")
            operator_name = get_payload_attr(payload, "_operator_name") or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 记录安全审计日志
            SysSecurityLogService(self.session).create_entry(
                operator_id=operator_id or 0,
                operator_name=operator_name,
                operator_ip=operator_ip,
                target_type="user",
                target_id=entity.id,
                target_name=entity.username,
                operation="create",
                module="user",
                resource_path=f"/admin/base/sys/user/{entity.id}",
                new_value=json.dumps(
                    {"username": entity.username, "full_name": entity.full_name, "email": entity.email},
                    ensure_ascii=False,
                ),
                business_type="user_management",
                status=1,
                remark="创建新用户",
            )
        except Exception as exc:
            logger.warning(f"记录用户创建审计日志失败 - user_id: {entity.id}", exc_info=exc)

        role_ids = get_payload_attr(payload, "role_ids")
        if role_ids is not None:
            self._replace_user_roles(entity.id, role_ids)

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] = (),
    ) -> list[UserListItem]:
        items = super().list(query, current_user, relations)
        return [UserListItem.model_validate(item) for item in items]

    def _row_to_dict(self, row: Any) -> dict:
        # 获取基础数据字典
        data = super()._row_to_dict(row)
        if not data:
            return {}
        # 处理 nick_name 默认值 (如果 DB 中为 NULL)
        if data.get("nick_name") is None:
            data["nick_name"] = data.get("full_name") or data.get("name") or data.get("username") or ""

        # 获取用户 ID 用于查询角色
        user_id = data.get("id")
        if user_id:
            roles = get_user_roles(self.session, user_id)
            data["role_ids"] = [role.id for role in roles if role.id is not None]
            data["role_name"] = ",".join(role.name for role in roles if role.name)
        else:
            data["role_ids"] = []
            data["role_name"] = ""

        return data

    # 钩子实现 (Hooks)
    def _before_add(self, data: dict) -> dict:
        username = data.get("username")
        existing = self.session.exec(select(User).where(User.username == username)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

        password = data.pop("password", None)
        if password:
            # 验证密码强度
            validate_password_strength(password)
            data["password_hash"] = hash_password(password)
        data["nick_name"] = data.get("nick_name", "") or data.get("full_name", "")
        data.pop("role_ids", None)
        return data

    def _before_update(self, data: dict, entity: User) -> dict:
        if data.get("password"):
            # 验证密码强度
            validate_password_strength(data["password"])
            data["password_hash"] = hash_password(data.pop("password"))
            entity.password_version += 1
            entity.password_changed_at = datetime.now(UTC)  # 记录密码修改时间
        else:
            data.pop("password", None)
        data["nick_name"] = data.get("nick_name", "") or data.get("full_name", entity.full_name)
        data.pop("role_ids", None)
        return data

    def _after_update(self, entity: User, payload: Any) -> None:
        """用户更新后记录安全审计日志"""
        # 仅依据"本次实际传入"的字段判断：部分更新时未传字段会取 DTO 默认值（如 is_active=True、
        # role_ids=[]），不能据默认值误判为"启用用户/清空角色"，否则任意单字段更新都会误触发。
        update_fields = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else {}
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            # 获取当前操作者信息
            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 检查是否有敏感操作需要记录
            sensitive_operations = []
            diff_data = {}

            # 检查是否禁用/启用用户（仅当本次显式传入 is_active）
            if "is_active" in update_fields:
                if not update_fields["is_active"]:
                    sensitive_operations.append("disable_user")
                    diff_data["is_active"] = {"old": "enabled", "new": "disabled"}
                else:
                    sensitive_operations.append("enable_user")
                    diff_data["is_active"] = {"old": "disabled", "new": "enabled"}

            # 检查是否重置密码
            if "password" in update_fields and update_fields["password"]:
                sensitive_operations.append("reset_password")
                diff_data["password"] = {"old": "******", "new": "******"}

            # 如果有敏感操作，记录审计日志
            if sensitive_operations:
                for op in sensitive_operations:
                    SysSecurityLogService(self.session).create_entry(
                        operator_id=operator_id or 0,
                        operator_name=operator_name,
                        operator_ip=operator_ip,
                        target_type="user",
                        target_id=entity.id,
                        target_name=entity.username,
                        operation=op,
                        module="user",
                        resource_path=f"/admin/base/sys/user/{entity.id}",
                        diff_data=json.dumps(diff_data, ensure_ascii=False),
                        business_type="user_management",
                        status=1,
                        remark=f"执行敏感操作: {', '.join(sensitive_operations)}",
                    )
        except Exception as exc:
            logger.warning(f"记录用户更新审计日志失败 - user_id: {entity.id}", exc_info=exc)

        # 仅当本次显式传入 role_ids 时才重置角色（避免部分更新用默认空列表误清空角色）
        if "role_ids" in update_fields:
            self._replace_user_roles(entity.id, payload.role_ids)

        # is_active 黑名单/登录缓存：仅当本次显式传入时才处理（避免部分更新误清登录缓存）
        if "is_active" in update_fields:
            if not update_fields["is_active"]:
                add_user_all_tokens_to_blacklist(entity.id)
            else:
                clear_login_caches(entity.id)

    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
        users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())
        protected_users = [user.username for user in users if user.is_super_admin]
        if protected_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"不能删除超级管理员: {', '.join(protected_users)}"
            )
        return ids

    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        """用户删除后记录安全审计日志及外部状态同步"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = get_payload_attr(payload, "_operator_id") or get_payload_attr(payload, "current_user_id") or 0
            operator_name = get_payload_attr(payload, "_operator_name") or "system"
            operator_ip = get_request_ip_from_payload(payload)

            for user_id in ids:
                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id,
                    operator_name=operator_name,
                    operator_ip=operator_ip,
                    target_type="user",
                    target_id=user_id,
                    target_name=str(user_id),
                    operation="delete",
                    module="user",
                    resource_path=f"/admin/base/sys/user/{user_id}",
                    business_type="user_management",
                    status=1,
                    remark="删除用户",
                )
        except Exception as exc:
            logger.warning(f"记录用户删除审计日志失败 - user_ids: {ids}", exc_info=exc)

        # 外部副作用：Token 加黑名单及清理登录缓存
        for user_id in ids:
            add_user_all_tokens_to_blacklist(user_id)
        clear_login_caches_for_users(ids)

    def _replace_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        existing_links = list(self.session.exec(select(UserRoleLink).where(UserRoleLink.user_id == user_id)).all())
        for link in existing_links:
            self.session.delete(link)
        if role_ids:
            roles = list(self.session.exec(select(Role).where(Role.id.in_(role_ids))).all())
            found_role_ids = {role.id for role in roles if role.id is not None}
            missing_ids = sorted(set(role_ids) - found_role_ids)
            if missing_ids:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {missing_ids}")
            for role_id in role_ids:
                self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))
        self.session.flush()

    def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
        user = self.session.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        with transaction(self.session):
            self._replace_user_roles(payload.user_id, payload.role_ids)
        clear_login_caches(payload.user_id)
        self.session.refresh(user)
        return UserListItem.model_validate(self._row_to_dict(user))

    def move(self, payload: dict | UserMoveRequest) -> dict:
        if isinstance(payload, dict):
            payload = UserMoveRequest(**payload)
        department = self.session.get(Department, payload.department_id)
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        users = list(self.session.exec(select(User).where(User.id.in_(payload.user_ids))).all())
        with transaction(self.session):
            for user in users:
                user.department_id = payload.department_id
                self.session.add(user)
        for user in users:
            clear_login_caches(user.id)
        return {"success": True}
