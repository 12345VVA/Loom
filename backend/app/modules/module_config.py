"""
模块配置定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PermissionConfig:
    """权限点定义"""

    name: str
    code: str
    permission: str
    admin_patterns: tuple[str, ...] = field(default_factory=tuple)
    type: str = "button"
    role_codes: tuple[str, ...] = ("admin",)


@dataclass(frozen=True)
class ResourceActionConfig:
    """资源动作定义"""

    suffix: str
    name: str
    methods: tuple[str, ...]
    path_patterns: tuple[str, ...]
    role_codes: tuple[str, ...] = ("admin",)
    type: str = "button"


@dataclass(frozen=True)
class ResourceConfig:
    """管理端资源定义"""

    module: str
    resource: str
    code_prefix: str
    name_prefix: str
    actions: tuple[ResourceActionConfig, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ModuleConfig:
    """模块元信息"""

    name: str
    label: str
    description: str = ""
    order: int = 0
    scopes: tuple[str, ...] = field(default_factory=tuple)
    bootstrap: str | None = None
    middlewares: tuple[type, ...] = field(default_factory=tuple)
    global_middlewares: tuple[type, ...] = field(default_factory=tuple)
    config_namespace: str | None = None
    init_db_file: str | None = None
    init_menu_file: str | None = None
    admin_whitelist: tuple[str, ...] = field(default_factory=tuple)
    app_whitelist: tuple[str, ...] = field(default_factory=tuple)
    aiapi_whitelist: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[PermissionConfig, ...] = field(default_factory=tuple)
    admin_resources: tuple[ResourceConfig, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MenuManifestItem:
    code: str
    name: str
    type: str = "menu"
    module: str | None = None
    resource: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    keep_alive: bool = True
    is_show: bool = True
    sort_order: int = 0
    parent_code: str | None = None
    role_codes: tuple[str, ...] = ("admin",)
    is_active: bool = True
    permission: str | None = None
    children: list[MenuManifestItem] = field(default_factory=list)


@dataclass(frozen=True)
class ModuleInitResource:
    module: str
    kind: str
    configured_path: str
    absolute_path: str
    exists: bool
    executed: bool = False
    handler: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ModuleMiddlewareBinding:
    module: str
    middleware: type
    prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ModuleRuntimeInfo:
    name: str
    label: str
    description: str
    scopes: tuple[str, ...]
    config_namespace: str | None
    config_values: dict[str, object]
    init_resources: tuple[ModuleInitResource, ...]
    module_root: str
    menu_manifest: tuple[MenuManifestItem, ...] = field(default_factory=tuple)


def resolve_module_root(module_name: str) -> Path:
    return Path(__file__).resolve().parent / module_name
