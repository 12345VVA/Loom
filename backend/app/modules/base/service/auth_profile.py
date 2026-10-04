"""用户资料与权限菜单域（AuthService 的 profile/menu 分域 mixin）。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.security import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.modules.base.compat import SYSTEM_MANAGED_CODE_PREFIXES
from app.modules.base.model.auth import (
    CoolMenuItem,
    CoolUserInfo,
    Menu,
    Role,
    User,
    UserPersonRead,
    UserPersonUpdateRequest,
)
from app.modules.base.service.admin_service import MenuAdminService
from app.modules.base.service.authority_service import clear_login_caches, clear_user_sessions
from app.modules.base.service.security_service import get_user_permissions, get_user_roles


class ProfileMixin:
    """个人资料、用户信息构建与权限菜单输出。依赖宿主提供 `self.session`。"""

    def get_current_profile(self, user: User) -> CoolUserInfo:
        roles = get_user_roles(self.session, user.id)
        permissions = get_user_permissions(self.session, user.id)
        # 检查是否需要强制修改密码
        force_password_change = user.password_changed_at is None
        return self.build_user_info(
            user, roles=roles, permissions=permissions, force_password_change=force_password_change
        )

    def build_user_info(
        self, user: User, roles: list[Role], permissions: list[str], force_password_change: bool = False
    ) -> CoolUserInfo:
        return CoolUserInfo(
            user_id=user.id,
            username=user.username,
            nick_name=user.full_name,
            department_id=user.department_id,
            role_codes=[role.code for role in roles],
            permission=permissions,
            is_super_admin=user.is_super_admin,
            force_password_change=force_password_change,
        )

    def person(self, user: User) -> UserPersonRead:
        return UserPersonRead(
            id=user.id,
            created_at=user.created_at,
            updated_at=user.updated_at or user.created_at,
            department_id=user.department_id,
            full_name=user.full_name,
            username=user.username,
            password_version=user.password_version,
            nick_name=user.nick_name,
            head_img=user.head_img,
            phone=user.phone,
            email=user.email,
            remark=user.remark,
            is_active=user.is_active,
            is_super_admin=1 if user.is_super_admin else 0,
            is_manager=1 if user.is_manager else 0,
            is_department_leader=1 if user.is_department_leader else 0,
        )

    def person_update(self, user: User, payload: UserPersonUpdateRequest) -> dict:
        target = self.session.get(User, user.id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        if payload.password:
            if not payload.old_password:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不能为空")
            if not verify_password(payload.old_password, target.password_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
            # 验证新密码强度
            validate_password_strength(payload.password)
            target.password_hash = hash_password(payload.password)
            target.password_version += 1
            target.password_changed_at = datetime.now(UTC)  # 记录密码修改时间

        if payload.nick_name is not None:
            target.nick_name = payload.nick_name
        if payload.head_img is not None:
            target.head_img = payload.head_img
        if payload.phone is not None:
            target.phone = payload.phone
        if payload.email is not None:
            target.email = payload.email
        if payload.remark is not None:
            target.remark = payload.remark

        target.updated_at = datetime.now(UTC)
        self.session.add(target)
        self.session.commit()
        self.session.refresh(target)
        clear_login_caches(target.id)
        # 改密码踢出全部设备：清空该用户所有会话记录
        # （旧 token 的 password_version 已不匹配，access/refresh 都会被拒；清 session 保持整洁）
        clear_user_sessions(target.id)
        return {"success": True}

    def permmenu(self, user: User) -> dict:
        """
        获取权限与菜单（Loom 兼容格式）

        返回格式: {"perms": list[str], "menus": list[dict]}

        重要: 菜单必须返回扁平数组结构，而非树形嵌套结构！
        - Loom 前端期望所有菜单项在同一层级，通过 parentId 字段建立父子关系
        - 每个菜单项的 children 数组必须为空 []
        - 测试用例 test_permmenu_contains_flat_system_management_routes 依赖此结构
        - 不要修改为树形结构，否则会导致前端无法正确渲染菜单

        Args:
            user: 当前用户

        Returns:
            dict: 包含 perms (权限列表) 和 menus (扁平菜单数组) 的字典
        """
        permissions = get_user_permissions(self.session, user.id)

        # 获取树形结构的菜单
        menu_tree = MenuAdminService(self.session).current_tree(user)

        # 转换为 CoolMenuItem 并扁平化，符合 Loom 前端期望的扁平数组格式
        cool_menus = [self._build_cool_menu_item(menu) for menu in menu_tree]
        flat_menus = self._flatten_cool_menus(cool_menus)

        return {
            "perms": permissions,
            "menus": [item.model_dump(mode="json", by_alias=True) for item in flat_menus],
        }

    def _build_cool_menu_item(
        self, menu, name_map: dict[int, str] | None = None, children_override: list = None
    ) -> CoolMenuItem:
        type_mapping = {"group": 0, "menu": 1, "button": 2}

        # 处理可能的模型对象或字典
        m_id = getattr(menu, "id", None)
        parent_id = getattr(menu, "parent_id", None)
        name = getattr(menu, "name", "")
        path = getattr(menu, "path", None)
        permission = getattr(menu, "permission", None)
        menu_type = getattr(menu, "type", 1)
        sort_order = getattr(menu, "sort_order", 0)
        component = getattr(menu, "component", None)
        keep_alive = getattr(menu, "keep_alive", True)
        is_show = getattr(menu, "is_show", True)
        is_active = getattr(menu, "is_active", True)
        # 如果传入了 children_override（来自树处理），则优先使用
        if children_override is not None:
            children = children_override
        else:
            children = getattr(menu, "children", getattr(menu, "child_menus", []))

        parent_name = None
        if name_map and parent_id in name_map:
            parent_name = name_map[parent_id]
        elif parent_id:
            parent_name = getattr(menu, "parent_name", None)

        final_type = type_mapping.get(menu_type, menu_type if isinstance(menu_type, int) else 1)

        # 处理组件路径逻辑，防止前端 Vue Router 报 Invalid route component
        if final_type == 0:  # 目录类型
            component = None
        elif final_type == 1:  # 菜单类型
            if not component or (isinstance(component, str) and not component.strip()):
                # 如果是带子菜单的父级菜单但没有定义组件，通常需要 layout 承载
                component = "layout" if children else None

        return CoolMenuItem(
            id=m_id,
            parent_id=parent_id,
            parent_name=parent_name,
            name=name,
            path=path,
            permission=permission,
            type=final_type,
            sort_order=sort_order,
            component=component,
            icon=getattr(menu, "icon", None),
            keep_alive=keep_alive,
            is_show=is_show,
            is_active=is_active,
            child_menus=[
                (self._build_cool_menu_item(child, name_map=name_map) if children_override is None else child)
                for child in children
            ],
        )

    def _flatten_cool_menus(self, menus: list[CoolMenuItem]) -> list[CoolMenuItem]:
        """
        将树形菜单结构扁平化

        将嵌套的树形菜单结构转换为扁平数组，每个菜单项的 child_menus 被清空。
        这是 Loom 前端框架的硬性要求，前端需要通过 parentId 字段自行构建树形结构。

        注意: 不要修改此方法的返回格式，否则会导致前端菜单无法正确渲染。

        Args:
            menus: 树形嵌套的菜单列表

        Returns:
            扁平化的菜单列表，每个菜单项的 child_menus 为空数组
        """
        result: list[CoolMenuItem] = []

        def walk(items: list[CoolMenuItem]) -> None:
            for item in items:
                children = item.child_menus
                result.append(item.model_copy(update={"child_menus": []}))
                if children:
                    walk(children)

        walk(menus)
        return result

    @staticmethod
    def _is_system_managed_menu(menu: Menu, managed_permissions: set[str], managed_paths: set[str]) -> bool:
        if menu.permission and menu.permission in managed_permissions:
            return True
        if menu.path and menu.path in managed_paths:
            return True
        code = menu.code or ""
        return any(code.startswith(prefix) for prefix in SYSTEM_MANAGED_CODE_PREFIXES)
