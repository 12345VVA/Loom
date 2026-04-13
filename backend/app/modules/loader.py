"""
模块启动加载器
"""
from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import os

from sqlmodel import Session

from app.framework.router.grouping import get_group_config
from app.modules.module_config import (
    MenuManifestItem,
    ModuleConfig,
    ModuleInitResource,
    ModuleMiddlewareBinding,
    ModuleRuntimeInfo,
    PermissionConfig,
    resolve_module_root,
)


def load_module_configs() -> list[ModuleConfig]:
    """自动发现并加载模块配置"""
    modules_root = Path(__file__).resolve().parent
    configs: list[ModuleConfig] = []

    for module_dir in sorted(path for path in modules_root.iterdir() if path.is_dir() and not path.name.startswith("__")):
        config_file = module_dir / "config.py"
        if not config_file.exists():
            continue
        module = import_module(f"app.modules.{module_dir.name}.config")
        configs.append(module.MODULE_CONFIG)

    return sorted(configs, key=lambda item: item.order, reverse=True)


def bootstrap_modules(session: Session) -> None:
    """执行模块启动初始化"""
    for config in load_module_configs():
        _execute_module_init_resources(config, session)
        if not config.bootstrap:
            continue
        module_path, _, attr_name = config.bootstrap.rpartition(".")
        target = getattr(import_module(module_path), attr_name)
        target(session)


def load_scope_whitelists() -> dict[str, set[str]]:
    """聚合所有模块声明的所有 Scope 白名单。"""
    whitelists: dict[str, set[str]] = {
        "admin": set(),
        "app": set(),
        "aiapi": set(),
        "public": set(),
    }
    
    for config in load_module_configs():
        # Admin 端口
        for path in config.admin_whitelist:
            whitelists["admin"].add(path.rstrip("/") or "/")
        
        # APP 端口
        for path in config.app_whitelist:
            whitelists["app"].add(path.rstrip("/") or "/")
            
        # AiApi 端口
        for path in config.aiapi_whitelist:
            whitelists["aiapi"].add(path.rstrip("/") or "/")
            
    return whitelists


def load_permission_configs() -> list[PermissionConfig]:
    """聚合所有模块权限定义。"""
    from app.framework.controller_meta import get_registered_permission_configs

    permissions = [
        permission
        for config in load_module_configs()
        for permission in config.permissions
    ]
    permissions.extend(get_registered_permission_configs())
    for config in load_module_configs():
        for resource in config.admin_resources:
            for action in resource.actions:
                permissions.append(
                    PermissionConfig(
                        name=f"{resource.name_prefix}{action.name}",
                        code=f"{resource.code_prefix}_{action.suffix}",
                        permission=f"{resource.module}:{resource.resource}:{action.suffix}",
                        admin_patterns=action.path_patterns,
                        type=action.type,
                        role_codes=action.role_codes,
                    )
                )
    unique_permissions: dict[str, PermissionConfig] = {}
    for permission in permissions:
        key = permission.permission or permission.code
        unique_permissions[key] = permission
    return list(unique_permissions.values())


def load_global_middlewares() -> list[type]:
    """聚合模块声明的全局中间件。"""
    ordered: list[type] = []
    seen: set[str] = set()
    for config in load_module_configs():
        for middleware in config.global_middlewares:
            identity = f"{middleware.__module__}.{middleware.__name__}"
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(middleware)
    return ordered


def load_menu_manifest_items() -> list[MenuManifestItem]:
    items: list[MenuManifestItem] = []
    for config in load_module_configs():
        if not config.init_menu_file:
            continue
        manifest = _load_menu_manifest(config)
        items.extend(manifest)
    return items


def load_module_middlewares() -> list[ModuleMiddlewareBinding]:
    bindings: list[ModuleMiddlewareBinding] = []
    for config in load_module_configs():
        prefixes = tuple(_build_module_prefixes(config))
        if not prefixes:
            continue
        for middleware in config.middlewares:
            bindings.append(
                ModuleMiddlewareBinding(
                    module=config.name,
                    middleware=middleware,
                    prefixes=prefixes,
                )
            )
    return bindings


def load_module_runtime_infos() -> list[ModuleRuntimeInfo]:
    return [_build_runtime_info(config) for config in load_module_configs()]


def _build_runtime_info(config: ModuleConfig) -> ModuleRuntimeInfo:
    module_root = resolve_module_root(config.name)
    return ModuleRuntimeInfo(
        name=config.name,
        label=config.label,
        description=config.description,
        scopes=config.scopes,
        config_namespace=config.config_namespace,
        config_values=_load_module_config_values(config.config_namespace),
        init_resources=tuple(_collect_module_init_resources(config)),
        menu_manifest=tuple(_load_menu_manifest(config)),
        module_root=str(module_root),
    )


def _load_menu_manifest(config: ModuleConfig) -> list[MenuManifestItem]:
    if not config.init_menu_file:
        return []
    resource = _build_module_init_resource(config, "menu", config.init_menu_file)
    if not resource.exists:
        return []
    suffix = Path(resource.absolute_path).suffix.lower()
    if suffix == ".py":
        module_path = f"app.modules.{config.name}.{Path(config.init_menu_file).with_suffix('').as_posix().replace('/', '.')}"
        module = import_module(module_path)
        raw_items = getattr(module, "MENU_ITEMS", ())
    elif suffix == ".json":
        raw_items = json.loads(Path(resource.absolute_path).read_text(encoding="utf-8"))
    else:
        return []
    def parse_items(items: list, parent_code: str | None = None) -> list[MenuManifestItem]:
        res: list[MenuManifestItem] = []
        for it in items:
            if isinstance(it, dict):
                # 如果没有显式设置 parent_code 且存在传入的 parent_code，则自动关联
                if parent_code and not it.get("parent_code"):
                    it["parent_code"] = parent_code
                
                children_data = it.pop("children", [])
                item_obj = MenuManifestItem(**it)
                res.append(item_obj)
                
                if children_data:
                    res.extend(parse_items(children_data, parent_code=item_obj.code))
            elif isinstance(it, MenuManifestItem):
                res.append(it)
        return res

    return parse_items(raw_items)


def _build_module_prefixes(config: ModuleConfig) -> list[str]:
    prefixes: list[str] = []
    for scope in config.scopes:
        group = get_group_config(scope)
        prefix = f"{group.prefix}/{config.name}".rstrip("/")
        if prefix:
            prefixes.append(prefix)
    return prefixes


def _load_module_config_values(namespace: str | None) -> dict[str, object]:
    if not namespace:
        return {}
    prefix = f"{namespace.upper()}_"
    values: dict[str, object] = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            values[key.removeprefix(prefix).lower()] = value
    return values


def _collect_module_init_resources(config: ModuleConfig) -> list[ModuleInitResource]:
    resources: list[ModuleInitResource] = []
    if config.init_db_file:
        resources.append(_build_module_init_resource(config, "db", config.init_db_file))
    if config.init_menu_file:
        resources.append(_build_module_init_resource(config, "menu", config.init_menu_file))
    return resources


def _build_module_init_resource(config: ModuleConfig, kind: str, relative_path: str) -> ModuleInitResource:
    module_root = resolve_module_root(config.name)
    absolute_path = (module_root / relative_path).resolve()
    return ModuleInitResource(
        module=config.name,
        kind=kind,
        configured_path=relative_path,
        absolute_path=str(absolute_path),
        exists=absolute_path.exists(),
        executed=False,
        detail="pending",
    )


def _execute_module_init_resources(config: ModuleConfig, session: Session) -> None:
    for resource in _collect_module_init_resources(config):
        if not resource.exists:
            continue
        suffix = Path(resource.absolute_path).suffix.lower()
        if suffix != ".py":
            continue
        module_path = f"app.modules.{config.name}.{Path(resource.configured_path).with_suffix('').as_posix().replace('/', '.')}"
        module = import_module(module_path)
        runner = getattr(module, "run", None) or getattr(module, "bootstrap", None)
        if runner:
            runner(session)
