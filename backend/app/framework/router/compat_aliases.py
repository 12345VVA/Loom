"""
Loom-vue 兼容路由别名

RESOURCE_COMPATS 数据自 base/compat.py 下沉至此（纯字符串数据、零 import 依赖，
依赖方向正转）；原 _build_dict_compat_router 兼容端点引用了不存在的 SysDict/
SysDictData 模型（请求即 ImportError，前端亦无调用），已删除。
"""

from __future__ import annotations

from collections.abc import Iterable  # noqa: F401  （别名消费方兼容保留）
from dataclasses import dataclass, field
from importlib import import_module

from fastapi import APIRouter

ROUTER_ALIASES: tuple[tuple[str, str], ...] = (
    ("app.modules.base.controller.admin.user", "/admin/base/sys/user"),
    ("app.modules.base.controller.admin.role", "/admin/base/sys/role"),
    ("app.modules.base.controller.admin.menu", "/admin/base/sys/menu"),
    ("app.modules.base.controller.admin.department", "/admin/base/sys/department"),
)


@dataclass(frozen=True)
class ResourceCompat:
    source_module: str
    source_resource: str
    compat_module: str
    compat_name: str
    compat_prefix: str
    menu_parent_code: str | None = None
    route_aliases: tuple[str, ...] = field(default_factory=tuple)


RESOURCE_COMPATS: tuple[ResourceCompat, ...] = (
    ResourceCompat("base", "sys/user", "base", "user", "/admin/base/sys/user", "nav_system_users"),
    ResourceCompat("base", "sys/role", "base", "role", "/admin/base/sys/role", "nav_system_roles"),
    ResourceCompat("base", "sys/menu", "base", "menu", "/admin/base/sys/menu", "nav_system_menus"),
    ResourceCompat("base", "sys/department", "base", "department", "/admin/base/sys/department", "nav_system_users"),
    ResourceCompat("base", "sys/param", "base", "param", "/admin/base/sys/param", "nav_system_params"),
    ResourceCompat("base", "sys/log", "base", "log", "/admin/base/sys/log", "nav_monitor_logs"),
    ResourceCompat("base", "sys/login_log", "base", "login_log", "/admin/base/sys/login_log", "nav_monitor_login_logs"),
    ResourceCompat("base", "comm", "base", "comm", "/admin/base/comm"),
    ResourceCompat("base", "open", "base", "open", "/admin/base/open"),
    ResourceCompat("dict", "type", "dict", "type", "/admin/dict/type", "nav_data_dict"),
    ResourceCompat("dict", "info", "dict", "info", "/admin/dict/info", "nav_data_dict"),
    ResourceCompat("task", "info", "task", "info", "/admin/task/info", "nav_task_list"),
)


def register_compat_aliases(api_router: APIRouter) -> None:
    for module_path, prefix in ROUTER_ALIASES:
        try:
            route_module = import_module(module_path)
        except ModuleNotFoundError:
            continue
        router = getattr(route_module, "router", None)
        if router is not None:
            api_router.include_router(router, prefix=prefix)

    for compat in RESOURCE_COMPATS:
        controller_suffix = compat.source_resource.split("/")[-1]
        module_path = f"app.modules.{compat.source_module}.controller.admin.{controller_suffix}"
        try:
            route_module = import_module(module_path)
        except ModuleNotFoundError:
            continue
        router = getattr(route_module, "router", None)
        if router is None:
            continue
        for alias in compat.route_aliases:
            api_router.include_router(router, prefix=alias)
