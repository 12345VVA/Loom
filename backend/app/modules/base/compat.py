"""
Loom 兼容配置
"""

from __future__ import annotations

DEFAULT_AUTHENTICATED_PERMISSIONS: tuple[str, ...] = (
    "base:sys:user:me",
    "base:session:logout",
    "base:comm:person",
    "base:comm:person_update",
    "base:comm:permmenu",
    "base:comm:upload",
    "base:comm:upload_mode",
    "media:asset:downloadToken",
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
}

SYSTEM_MANAGED_CODE_PREFIXES: tuple[str, ...] = (
    "nav_",
    "base_",
    "dict_",
    "task_",
    "sys_",
    "common_",
    "data_",
    "home_",
)


# ResourceCompat / RESOURCE_COMPATS 已下沉 app.framework.router.compat_aliases
# （纯数据零 import 依赖，依赖方向正转），此处 re-export 兼容既有引用。
from app.framework.router.compat_aliases import (  # noqa: E402,F401
    RESOURCE_COMPATS,
    ResourceCompat,
)


def get_resource_compat(module: str, resource: str) -> ResourceCompat | None:
    return next(
        (item for item in RESOURCE_COMPATS if item.source_module == module and item.source_resource == resource),
        None,
    )


def get_menu_parent_code(module: str, resource: str) -> str | None:
    compat = get_resource_compat(module, resource)
    return compat.menu_parent_code if compat else None
