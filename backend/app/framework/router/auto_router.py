"""
按模块目录约定自动加载路由
"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

from fastapi import APIRouter

from app.framework.router.compat_aliases import register_compat_aliases
from app.framework.router.grouping import get_group_config


def create_api_router() -> APIRouter:
    """扫描 app.modules 下的控制器并自动注册路由"""
    api_router = APIRouter()
    _mount_convention_module_routes(api_router)
    register_compat_aliases(api_router)
    return api_router


def _mount_convention_module_routes(api_router: APIRouter) -> None:
    """挂载 app.modules 下符合约定的模块控制器"""
    modules_root = Path(__file__).resolve().parents[2] / "modules"
    if not modules_root.exists():
        return

    scope_alias = {
        "admin": "admin",
        "app": "app",
        "aiapi": "aiapi",
        "open": "public",
        "public": "public",
    }

    for module_dir in sorted(path for path in modules_root.iterdir() if path.is_dir() and not path.name.startswith("__")):
        controller_root = module_dir / "controller"
        if not controller_root.exists():
            continue

        for scope_dir in sorted(path for path in controller_root.iterdir() if path.is_dir() and path.name in scope_alias):
            group_name = scope_alias[scope_dir.name]
            group_config = get_group_config(group_name)

            for route_file in sorted(scope_dir.rglob("*.py")):
                if route_file.name == "__init__.py":
                    continue

                relative_parts = route_file.relative_to(scope_dir).with_suffix("").parts
                resource_prefix = "/" + "/".join((module_dir.name, *relative_parts))
                module_path = ".".join(("app", "modules", module_dir.name, "controller", scope_dir.name, *relative_parts))
                route_module = import_module(module_path)
                module_router = getattr(route_module, "router", None)
                if module_router is None:
                    continue

                api_router.include_router(
                    module_router,
                    prefix=f"{group_config.prefix}{resource_prefix}",
                    tags=list(group_config.tags),
                )
