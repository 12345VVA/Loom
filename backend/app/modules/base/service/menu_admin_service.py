"""
菜单资源管理服务（由 admin_service.py 门面 re-export）。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.database import transaction
from app.modules.base.compat import get_menu_parent_code, get_resource_compat
from app.modules.base.model.auth import (
    Menu,
    MenuCreateAutoItem,
    MenuCreateAutoRequest,
    MenuCreateRequest,
    MenuExportRequest,
    MenuImportNode,
    MenuImportRequest,
    MenuParseItem,
    MenuParseRequest,
    MenuRead,
    MenuTreeItem,
    MenuUpdateRequest,
    RoleMenuLink,
    User,
)
from app.modules.base.service.admin_base import BaseAdminCrudService
from app.modules.base.service.authority_service import clear_login_caches_for_menus

logger = logging.getLogger(__name__)


class MenuAdminService(BaseAdminCrudService):
    """菜单资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Menu)

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)
        data["type"] = self._normalize_menu_type_int(data.get("type", "button"))

        # 补充 parent_name
        if data.get("parent_id"):
            parent = self.session.get(Menu, data["parent_id"])
            if parent:
                data["parent_name"] = parent.name
        return data

    def _validate_parent_id(self, parent_id: int | None, menu_id: int | None = None) -> None:
        """校验 parent_id 对应的父菜单存在且不形成环（P1-11）。

        Args:
            parent_id: 待设置的父菜单 id；None 表示根菜单，直接放行。
            menu_id: 当前菜单 id；add 时为 None（新菜单无子孙，不会成环），
                update 时为当前菜单 id，用于祖先链环路检测。

        Raises:
            HTTPException: 400 当父菜单指向自身、不存在或会形成环路时。
        """
        if parent_id is None:
            return

        # 指向自身
        if menu_id is not None and parent_id == menu_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="父级菜单不能指向自身",
            )

        # 父菜单必须存在（且未软删除：session.get 不过滤 delete_time）
        parent = self.session.exec(select(Menu).where(Menu.id == parent_id, Menu.delete_time.is_(None))).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="父级菜单不存在",
            )

        # 环路检查：从 parent_id 向上遍历祖先链，若遇到 menu_id 则形成环
        if menu_id is None:
            return

        visited: set[int] = set()
        current_id: int | None = parent_id
        while current_id is not None:
            if current_id in visited:
                # 防御：祖先链本身已有环（历史脏数据），避免无限循环
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="菜单祖先链存在环，无法校验",
                )
            if current_id == menu_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="父级菜单设置将形成环路",
                )
            visited.add(current_id)
            ancestor = self.session.exec(select(Menu).where(Menu.id == current_id, Menu.delete_time.is_(None))).first()
            if not ancestor:
                break
            current_id = ancestor.parent_id

    def _before_add(self, data: dict) -> dict:
        code = data.get("code") or self._generate_menu_code(data)
        existing = self.session.exec(select(Menu).where(Menu.code == code)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")

        data["code"] = code
        data["type"] = self._normalize_menu_type(data.get("type"))
        # 校验父菜单存在（add 时新菜单尚无 id，不会形成环）
        self._validate_parent_id(data.get("parent_id"))
        return data

    def _before_update(self, data: dict, entity: Menu) -> dict:
        if "code" in data:
            code = data["code"]
            duplicate = self.session.exec(select(Menu).where((Menu.id != entity.id) & (Menu.code == code))).first()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")

        if "type" in data:
            data["type"] = self._normalize_menu_type(data["type"])
        # 仅当 parent_id 被实际更新时校验存在性与环路
        if "parent_id" in data:
            self._validate_parent_id(data.get("parent_id"), menu_id=entity.id)
        return data

    def _after_add(self, entity: Menu, payload: Any = None) -> None:
        self._clear_menu_related_caches([entity.id])

    def _after_update(self, entity: Menu, payload: Any = None) -> None:
        self._clear_menu_related_caches([entity.id])

    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        self._clear_menu_related_caches(ids)

    def tree(self) -> list[dict]:
        return self.list(is_tree=True)

    def role_menu_ids(self, role_id: int) -> list[int]:
        return [
            link.menu_id
            for link in self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role_id)).all()
        ]

    def export(self, payload: MenuExportRequest | dict) -> list[dict]:
        if isinstance(payload, dict):
            payload = MenuExportRequest(**payload)
        menu_ids = self._collect_descendant_ids(payload.ids)
        menus = list(
            self.session.exec(
                select(Menu).where(Menu.id.in_(menu_ids)).order_by(Menu.sort_order.asc(), Menu.created_at.asc())
            ).all()
        )
        tree = self._build_import_tree(menus)
        selected_ids = set(payload.ids)
        result = [node for node in tree if node.id in selected_ids]
        return [item.model_dump(mode="json", by_alias=True) for item in result]

    def import_menu(self, payload: MenuImportRequest | dict) -> dict:
        if isinstance(payload, dict):
            payload = MenuImportRequest(**payload)
        with transaction(self.session):
            for item in payload.menus:
                self._upsert_import_node(item, None)
        self._clear_menu_related_caches(list(self.session.exec(select(Menu.id)).all()))
        return {"success": True}

    def create_auto(self, payload: MenuCreateAutoRequest | dict) -> list[MenuRead]:
        if isinstance(payload, dict):
            payload = MenuCreateAutoRequest(**payload)
        created_menus: list[Menu] = []
        with transaction(self.session):
            for item in payload.items:
                created_menus.append(self._upsert_auto_menu(item))
        for menu in created_menus:
            self.session.refresh(menu)
            self._clear_menu_related_caches([menu.id])
        return [self._build_menu_read(menu) for menu in created_menus]

    def parse_menu_candidates(self, payload: MenuParseRequest, eps_catalog: dict[str, list[dict[str, Any]]]) -> dict:
        prefixes = set(payload.prefixes)
        items: list[dict[str, Any]] = []
        for module_name, controllers in eps_catalog.items():
            for controller in controllers:
                prefix = controller.get("prefix") or ""
                if prefixes and prefix not in prefixes and controller.get("name") not in prefixes:
                    continue
                resource = self._infer_resource_from_prefix(prefix)
                if not resource:
                    continue
                items.append(
                    MenuParseItem(
                        module=module_name,
                        resource=resource,
                        prefix=prefix,
                        controller=controller.get("name") or resource.split("/")[-1],
                        name=self._guess_menu_name(controller.get("name") or resource.split("/")[-1]),
                        path=self._build_router_from_resource(module_name, resource),
                        component=self._build_view_path_from_resource(module_name, resource),
                        icon=None,
                        parent_code=get_menu_parent_code(module_name, resource),
                        api=[
                            {
                                "name": api.get("name"),
                                "method": api.get("method"),
                                "path": api.get("path"),
                                "summary": self._guess_action_summary(api.get("name"), api.get("path")),
                                "permission": self._build_permission_from_resource(
                                    module_name, resource, api.get("name"), api.get("path")
                                ),
                            }
                            for api in controller.get("api", [])
                        ],
                    ).model_dump(mode="json", by_alias=True)
                )
        items.sort(key=lambda entry: (entry["module"], entry["resource"], entry["router"]))
        return {"list": items}

    def _build_menu_read(self, menu: Menu, parent_name: str | None = None) -> MenuRead:
        """构建菜单响应对象"""
        return MenuRead.model_validate(menu).model_copy(update={"parent_name": parent_name})

    @staticmethod
    def _normalize_menu_type_int(value: str | int) -> int:
        if value in (0, "0", "group", "dir"):
            return 0
        if value in (1, "1", "menu"):
            return 1
        return 2

    def current_tree(self, current_user: User) -> list[MenuTreeItem]:
        statement = select(Menu).where(Menu.is_active == True)  # noqa: E712
        if not current_user.is_super_admin:
            from app.modules.base.service.authority_service import get_user_roles

            role_ids = [role.id for role in get_user_roles(self.session, current_user.id) if role.id is not None]
            if not role_ids:
                return []
            statement = (
                select(Menu)
                .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
                .where(RoleMenuLink.role_id.in_(role_ids), Menu.is_active == True)  # noqa: E712
            )
        menus = list(self.session.exec(statement.order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())
        navigation_menus = [menu for menu in menus if menu.type in {"menu", "group"} or menu.path]
        expanded: dict[int, Menu] = {menu.id: menu for menu in navigation_menus}
        for menu in navigation_menus:
            parent_id = menu.parent_id
            while parent_id is not None:
                parent = self.session.get(Menu, parent_id)
                if not parent or not parent.is_active:
                    break
                expanded[parent.id] = parent
                parent_id = parent.parent_id

        # 预加载所有涉及到的节点的父级名称
        name_map = {m.id: m.name for m in expanded.values()}
        menu_list = sorted(expanded.values(), key=lambda item: (item.sort_order, item.created_at))

        # 构建树时，我们需要一个能够传递 parent_name 的 build_tree
        return self._build_tree_with_names(menu_list, name_map)

    def _build_tree_with_names(self, menus: list[Menu], name_map: dict[int, str]) -> list[MenuTreeItem]:
        nodes = {
            menu.id: MenuTreeItem(
                **self._build_menu_read(menu, parent_name=name_map.get(menu.parent_id)).model_dump(by_alias=True)
            )
            for menu in menus
        }
        children_map: dict[int | None, list[MenuTreeItem]] = defaultdict(list)
        for menu in menus:
            children_map[menu.parent_id].append(nodes[menu.id])
        for parent_id, children in children_map.items():
            children.sort(key=lambda item: (item.sort_order, item.created_at))
            if parent_id in nodes:
                nodes[parent_id].children = children
        return children_map.get(None, [])

    def current_list(self, current_user: User) -> list[MenuRead]:
        """获取当前用户授权的扁平菜单列表"""
        statement = select(Menu).where(Menu.is_active == True)  # noqa: E712
        if not current_user.is_super_admin:
            from app.modules.base.service.authority_service import get_user_roles

            role_ids = [role.id for role in get_user_roles(self.session, current_user.id) if role.id is not None]
            if not role_ids:
                return []
            statement = (
                select(Menu)
                .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
                .where(RoleMenuLink.role_id.in_(role_ids), Menu.is_active == True)  # noqa: E712
            )
        menus = list(self.session.exec(statement.order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())

        # 预加载父级名称以提高性能
        menu_map = {menu.id: menu for menu in menus}
        # 如果是超管，可能需要所有菜单的名称，如果不是，只需在授权范围内的
        # 为了保险起见，如果有 parent_id 不在 menu_map 中，我们再查一下数据库
        all_parent_ids = {menu.parent_id for menu in menus if menu.parent_id is not None}
        missing_parent_ids = all_parent_ids - set(menu_map.keys())
        if missing_parent_ids:
            extra_parents = list(self.session.exec(select(Menu).where(Menu.id.in_(list(missing_parent_ids)))).all())
            for p in extra_parents:
                menu_map[p.id] = p

        return [
            self._build_menu_read(
                menu, parent_name=menu_map[menu.parent_id].name if menu.parent_id in menu_map else None
            )
            for menu in menus
        ]

    @staticmethod
    def _normalize_menu_type(value: int | str) -> str:
        if value in (0, "0", "group", "dir"):
            return "group"
        if value in (1, "1", "menu"):
            return "menu"
        return "button"

    def _generate_menu_code(self, payload: MenuCreateRequest | MenuUpdateRequest) -> str:
        seed = payload.code or payload.path or payload.permission or payload.name
        return self._next_unique_code(self._slugify(seed))

    def _generate_import_code(self, node: MenuImportNode) -> str:
        seed = node.path or node.permission or node.name
        return self._next_unique_code(self._slugify(seed))

    def _build_import_tree(self, menus: list[Menu]) -> list[MenuImportNode]:
        nodes = {
            menu.id: MenuImportNode(
                id=menu.id,
                parent_id=menu.parent_id,
                name=menu.name,
                path=menu.path,
                component=menu.component,
                permission=menu.permission,
                type=self._normalize_menu_type_int(menu.type),
                icon=menu.icon,
                sort_order=menu.sort_order,
                keep_alive=menu.keep_alive,
                is_show=menu.is_show,
            )
            for menu in menus
            if menu.id is not None
        }
        roots: list[MenuImportNode] = []
        for menu in sorted(menus, key=lambda item: (item.sort_order, item.created_at)):
            if menu.id is None or menu.id not in nodes:
                continue
            node = nodes[menu.id]
            parent = nodes.get(menu.parent_id)
            if parent is None:
                roots.append(node)
            else:
                parent.child_menus.append(node)
        return roots

    def _upsert_import_node(self, node: MenuImportNode, parent_id: int | None) -> Menu:
        menu = self.session.get(Menu, node.id) if node.id is not None else None
        if menu is None and node.permission:
            menu = self.session.exec(select(Menu).where(Menu.permission == node.permission)).first()
        if menu is None and node.path:
            menu = self.session.exec(select(Menu).where(Menu.path == node.path, Menu.type != "button")).first()
        if menu is None:
            menu = Menu(code=self._generate_import_code(node), name=node.name)

        menu.parent_id = parent_id
        menu.name = node.name
        menu.path = node.path
        menu.component = node.component
        menu.permission = node.permission
        menu.type = self._normalize_menu_type(node.type)
        menu.icon = node.icon
        menu.sort_order = node.sort_order
        menu.keep_alive = node.keep_alive
        menu.is_show = node.is_show
        menu.is_active = True
        self.session.add(menu)
        self.session.flush()

        for child in node.child_menus:
            self._upsert_import_node(child, menu.id)
        return menu

    @staticmethod
    def _build_view_path(item: MenuCreateAutoItem) -> str | None:
        if item.component:
            return item.component
        if item.module and item.path:
            suffix = item.path.replace(f"/{item.module}", "")
            return f"modules/{item.module}/views{suffix}.vue"
        return None

    @staticmethod
    def _build_auto_permission(item: MenuCreateAutoItem, path: str) -> str:
        prefix = (item.prefix or "").replace("/admin/", "")
        return f"{prefix}{path}".replace("/", ":").strip(":")

    def _upsert_auto_menu(self, item: MenuCreateAutoItem) -> Menu:
        menu = self.session.exec(select(Menu).where(Menu.path == item.path, Menu.type == "menu")).first()
        if menu is None:
            menu = Menu(code=self._next_unique_code(self._slugify(item.path or item.name)), name=item.name)

        menu.parent_id = item.parent_id
        menu.name = item.name
        menu.type = "menu"
        menu.path = item.path
        menu.component = item.component or self._build_view_path(item)
        menu.icon = item.icon
        menu.keep_alive = item.keep_alive
        menu.is_show = True
        menu.sort_order = item.sort_order
        menu.is_active = True
        menu.updated_at = datetime.now(UTC)
        self.session.add(menu)
        self.session.flush()

        for index, api in enumerate(item.api, start=1):
            perms = api.get("permission") or self._build_auto_permission(item, api.get("path") or "")
            if not perms:
                continue
            button = self.session.exec(select(Menu).where(Menu.permission == perms)).first()
            if button is None:
                button = Menu(
                    code=self._next_unique_code(self._slugify(perms)),
                    name=api.get("summary") or api.get("name") or "权限",
                )
            button.parent_id = menu.id
            button.name = api.get("summary") or api.get("name") or "权限"
            button.type = "button"
            button.path = None
            button.component = None
            button.icon = None
            button.keep_alive = False
            button.is_show = True
            button.permission = perms
            button.sort_order = index
            button.is_active = True
            button.updated_at = datetime.now(UTC)
            self.session.add(button)
        self.session.flush()
        return menu

    def _next_unique_code(self, base: str) -> str:
        candidate = base or "menu"
        index = 1
        while True:
            existing = self.session.exec(select(Menu).where(Menu.code == candidate)).first()
            if existing is None:
                return candidate
            index += 1
            candidate = f"{base}_{index}"

    @staticmethod
    def _slugify(value: str | None) -> str:
        raw = (value or "menu").strip().lower().replace(":", "_").replace("/", "_").replace("-", "_")
        normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized.strip("_") or "menu"

    @staticmethod
    def _infer_resource_from_prefix(prefix: str) -> str | None:
        normalized = prefix.rstrip("/")
        if not normalized.startswith("/admin/"):
            return None
        parts = normalized.removeprefix("/admin/").split("/")
        if len(parts) < 2:
            return None
        return "/".join(parts[1:])

    @staticmethod
    def _guess_menu_name(name: str) -> str:
        mapping = {
            "user": "用户管理",
            "role": "角色管理",
            "menu": "菜单管理",
            "department": "部门管理",
            "param": "参数配置",
            "log": "请求日志",
            "login_log": "登录日志",
            "type": "字典管理",
            "info": "任务列表",
        }
        return mapping.get(name, name)

    @staticmethod
    def _guess_action_summary(name: str | None, path: str | None) -> str:
        action = name or (path or "").rstrip("/").split("/")[-1]
        mapping = {
            "list": "列表查询",
            "page": "分页查询",
            "info": "详情",
            "add": "新增",
            "update": "修改",
            "delete": "删除",
            "assignRoles": "分配角色",
            "assignMenus": "分配菜单",
            "roleMenuIds": "角色菜单",
            "tree": "菜单树",
            "currentTree": "当前菜单树",
            "export": "导出",
            "import": "导入",
            "parse": "解析菜单",
            "create": "创建菜单",
            "order": "排序",
            "cancel": "取消任务",
            "stats": "任务统计",
            "move": "移动部门",
        }
        return mapping.get(action, action or "权限")

    @staticmethod
    def _build_router_from_resource(module: str, resource: str) -> str:
        compat = get_resource_compat(module, resource)
        if compat and compat.compat_module == "task":
            return "/task/list"
        return f"/{module}/{resource}".replace("//", "/")

    @staticmethod
    def _build_view_path_from_resource(module: str, resource: str) -> str | None:
        compat = get_resource_compat(module, resource)
        if compat and compat.compat_module == "task":
            return "modules/task/views/list.vue"
        if module == "base" and resource == "sys/user":
            return "modules/base/views/user/index.vue"
        if module == "base":
            return f"modules/base/views/{resource.split('/')[-1]}.vue"
        if module == "dict":
            return "modules/dict/views/list.vue"
        return f"modules/{module}/views/{resource.split('/')[-1]}.vue"

    @staticmethod
    def _build_permission_from_resource(module: str, resource: str, name: str | None, path: str | None) -> str | None:
        action = name or (path or "").rstrip("/").split("/")[-1]
        if not action:
            return None
        return f"{module}:{resource.replace('/', ':')}:{action}"

    def _clear_menu_related_caches(self, menu_ids: list[int]) -> None:
        """从 AuthorityService 聚合清理菜单相关的权限缓存"""
        clear_login_caches_for_menus(self.session, menu_ids)
