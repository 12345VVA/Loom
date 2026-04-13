"""
Cool 兼容配置
"""
from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_AUTHENTICATED_PERMISSIONS: tuple[str, ...] = (
    "base:sys:user:me",
    "base:session:logout",
    "base:comm:person",
    "base:comm:person_update",
    "base:comm:permmenu",
    "base:comm:upload",
    "base:comm:upload_mode",
)

DEFAULT_PUBLIC_PERMISSION_PATHS: tuple[str, ...] = (
    "base/comm/person",
    "base/comm/personUpdate",
    "base/comm/permmenu",
    "base/comm/upload",
    "base/comm/uploadMode",
    "dict/info/data",
    "dict/info/types",
)

ADMIN_PATH_ALIASES: dict[str, str] = {
    "/admin/base/user": "/admin/base/sys/user",
    "/admin/base/role": "/admin/base/sys/role",
    "/admin/base/menu": "/admin/base/sys/menu",
    "/admin/base/department": "/admin/base/sys/department",
    "/admin/base/sys/dict": "/admin/dict/type",
    "/admin/base/sys/dict_data": "/admin/dict/info",
    "/admin/task/task": "/admin/task/info",
    "/admin/task_ai/info": "/admin/task/info",
}

SYSTEM_MANAGED_CODE_PREFIXES: tuple[str, ...] = (
    "nav_",
    "base_",
    "dict_",
    "task_",
    "task_ai_",
    "sys_",
    "common_",
    "data_",
    "home_",
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
    ResourceCompat("task_ai", "info", "task", "info", "/admin/task/info", "nav_task_list", route_aliases=("/admin/task_ai/info",)),
    ResourceCompat("task", "info", "task", "info", "/admin/task/info", "nav_task_list"),
)


def get_resource_compat(module: str, resource: str) -> ResourceCompat | None:
    return next(
        (
            item
            for item in RESOURCE_COMPATS
            if item.source_module == module and item.source_resource == resource
        ),
        None,
    )


def get_menu_parent_code(module: str, resource: str) -> str | None:
    compat = get_resource_compat(module, resource)
    return compat.menu_parent_code if compat else None
