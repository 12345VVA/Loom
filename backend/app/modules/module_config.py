"""模块配置定义——已下沉 framework（依赖方向正转），本文件为兼容 re-export。"""

from app.framework.module_config import (  # noqa: F401
    MenuManifestItem,
    ModuleConfig,
    ModuleInitResource,
    ModuleMiddlewareBinding,
    ModuleRuntimeInfo,
    PermissionConfig,
    ResourceActionConfig,
    ResourceConfig,
    resolve_module_root,
)

__all__ = [
    "MenuManifestItem",
    "ModuleConfig",
    "ModuleInitResource",
    "ModuleMiddlewareBinding",
    "ModuleRuntimeInfo",
    "PermissionConfig",
    "ResourceActionConfig",
    "ResourceConfig",
    "resolve_module_root",
]
