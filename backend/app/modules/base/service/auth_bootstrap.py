"""启动引导域（AuthService 的 bootstrap 分域 mixin）：菜单/角色/初始账号幂等对账。"""

from __future__ import annotations

from sqlmodel import select

from app.core.config import settings
from app.core.database import transaction
from app.core.security import hash_password
from app.modules.base.model.auth import (
    Department,
    Menu,
    Role,
    RoleDepartmentLink,
    RoleMenuLink,
    User,
    UserRoleLink,
)
from app.modules.base.service.authority_service import clear_login_caches_for_users
from app.modules.loader import load_menu_manifest_items


class BootstrapMixin:
    """启动期初始化对账。依赖宿主提供 `self.session`。"""

    def bootstrap_defaults(self) -> None:
        """菜单/角色/初始账号的全量对账（幂等，可重复调用）。

        单事务批量 upsert：此前逐条 select + commit（240 菜单 × 每条一次
        磁盘同步）是启动与测试 lifespan 的最大热点（PG 实测 ~10s）。
        SQLAlchemy unit of work 对未变更对象自动零 SQL，稳态重跑仅一次空 commit。
        """
        with transaction(self.session):
            root_department = self.session.exec(select(Department).where(Department.name == "平台")).first()
            if not root_department:
                root_department = Department(name="平台", sort_order=0)
                self.session.add(root_department)

            admin_role = self.session.exec(select(Role).where(Role.code == "admin")).first()
            if not admin_role:
                admin_role = Role(name="系统管理员", code="admin", label="admin", data_scope="all")
                self.session.add(admin_role)

            operator_role = self.session.exec(select(Role).where(Role.code == "task_operator")).first()
            if not operator_role:
                operator_role = Role(
                    name="任务操作员",
                    code="task_operator",
                    label="task_operator",
                    data_scope="self",
                )
                self.session.add(operator_role)

            role_map = {
                admin_role.code: admin_role,
                operator_role.code: operator_role,
            }

            navigation_definitions = load_menu_manifest_items()

            all_valid_codes: set[str] = {item.code for item in navigation_definitions}
            managed_permissions: set[str] = {item.permission for item in navigation_definitions if item.permission}
            managed_paths: set[str] = {item.path for item in navigation_definitions if item.path}

            # 全量一次替代逐菜单 select；后建菜单不入此映射（必然命中
            # all_valid_codes，与下方清扫无关）
            existing_menus: dict[str, Menu] = {m.code: m for m in self.session.exec(select(Menu)).all()}
            menus_by_code: dict[str, Menu] = {}
            for item in navigation_definitions:
                menu = existing_menus.get(item.code)
                if not menu:
                    menu = Menu(
                        name=item.name,
                        code=item.code,
                        type=item.type,
                        path=item.path,
                        component=item.component,
                        icon=item.icon,
                        keep_alive=item.keep_alive,
                        is_show=item.is_show,
                        sort_order=item.sort_order,
                        is_active=item.is_active,
                        permission=item.permission,
                    )
                else:
                    # 无条件覆写以对齐 manifest；unit of work 只对脏字段发 UPDATE
                    menu.name = item.name
                    menu.type = item.type
                    menu.path = item.path
                    menu.component = item.component
                    menu.icon = item.icon
                    menu.keep_alive = item.keep_alive
                    menu.is_show = item.is_show
                    menu.sort_order = item.sort_order
                    menu.is_active = item.is_active
                    menu.permission = item.permission
                self.session.add(menu)
                menus_by_code[item.code] = menu

            # 一次 flush 让全部新对象拿到自增 id（替代原逐条 commit+refresh）
            self.session.flush()

            for item in navigation_definitions:
                menu = menus_by_code[item.code]
                parent_code = item.parent_code
                if parent_code:
                    parent_menu = menus_by_code[parent_code]
                    desired_parent_id = parent_menu.id
                else:
                    # parent_code 为空表示该菜单应作为顶级节点；
                    # 需主动清空已存在的 parent_id，否则历史挂载关系无法回滚
                    # （例如将分组从“系统管理”下提升为一级菜单）
                    desired_parent_id = None
                if menu.parent_id != desired_parent_id:
                    menu.parent_id = desired_parent_id

            # 角色-菜单绑定：全量判重、缺失才补（link 表无联合唯一，去重必须在内存）
            existing_links: dict[tuple[int, int], RoleMenuLink] = {
                (link.role_id, link.menu_id): link for link in self.session.exec(select(RoleMenuLink)).all()
            }
            for item in navigation_definitions:
                menu = menus_by_code[item.code]
                for role_code in item.role_codes:
                    role = role_map.get(role_code)
                    if role and role.id is not None and menu.id is not None:
                        key = (role.id, menu.id)
                        if key not in existing_links:
                            link = RoleMenuLink(role_id=role.id, menu_id=menu.id)
                            existing_links[key] = link
                            self.session.add(link)

            # 清理数据库中不再存在（既不在 JSON Manifest 中，也不在控制器扫描结果中）的权限记录
            for db_menu in list(existing_menus.values()):
                if db_menu.code not in all_valid_codes and self._is_system_managed_menu(
                    db_menu, managed_permissions, managed_paths
                ):
                    # 删除与之关联的角色绑定，防止悬挂引用
                    for key in [k for k in existing_links if k[1] == db_menu.id]:
                        self.session.delete(existing_links.pop(key))
                    self.session.delete(db_menu)

            if admin_role.id is not None and root_department.id is not None:
                self._ensure_role_department_link(admin_role.id, root_department.id)
            if operator_role.id is not None and root_department.id is not None:
                self._ensure_role_department_link(operator_role.id, root_department.id)

            admin_user = self.session.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
            if not admin_user:
                admin_user = User(
                    username=settings.DEFAULT_ADMIN_USERNAME.strip(),
                    full_name=settings.DEFAULT_ADMIN_NAME,
                    password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD.strip()),
                    department_id=root_department.id,
                    is_super_admin=True,
                    is_manager=True,
                    is_department_leader=True,
                )
                self.session.add(admin_user)
                # ensure_user_role_link 需要 admin_user.id，先 flush 落库
                self.session.flush()

            if admin_user.id is not None and admin_role.id is not None:
                self._ensure_user_role_link(admin_user.id, admin_role.id)

        # 同步完成后清理全站权限缓存，确保新菜单生效（非 DB 操作，移出事务）
        all_user_ids = self.session.exec(select(User.id)).all()
        clear_login_caches_for_users(all_user_ids)

    def _ensure_user_role_link(self, user_id: int, role_id: int) -> None:
        """缺则补一条绑定；不提交，事务由调用方（bootstrap_defaults 的 transaction）管理。"""
        link = self.session.exec(
            select(UserRoleLink).where(UserRoleLink.user_id == user_id, UserRoleLink.role_id == role_id)
        ).first()
        if not link:
            self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))

    def _ensure_role_department_link(self, role_id: int, department_id: int) -> None:
        """缺则补一条绑定；不提交，事务由调用方（bootstrap_defaults 的 transaction）管理。"""
        link = self.session.exec(
            select(RoleDepartmentLink).where(
                RoleDepartmentLink.role_id == role_id, RoleDepartmentLink.department_id == department_id
            )
        ).first()
        if not link:
            self.session.add(RoleDepartmentLink(role_id=role_id, department_id=department_id))
