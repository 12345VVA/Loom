"""
EPS 服务扫描导出
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.framework.controller_meta import get_registered_exported_routes
from app.framework.eps.scanner import scan_model_columns
from app.modules.base.compat import get_resource_compat


class EpsService:
    def __init__(self, app: FastAPI):
        self.app = app

    def export(self) -> dict[str, Any]:
        openapi = self.app.openapi()
        path_map = openapi.get("paths", {})
        module_meta = getattr(self.app.state, "cool_module", {})
        result: dict[str, Any] = {"admin": {}, "app": {}, "module": module_meta}

        for route in get_registered_exported_routes():
            scope_bucket = result["admin" if route.scope == "admin" else "app" if route.scope == "app" else "admin"]
            module_name = route.module
            scope_bucket.setdefault(module_name, [])

            controller = next((item for item in scope_bucket[module_name] if item["name"] == route.controller_name), None)
            if controller is None:
                compat = get_resource_compat(route.module, route.resource)
                prefix = compat.compat_prefix if compat else f"/{route.scope}/{module_name}/{str(route.resource).replace(':', '/').replace('.', '/')}"
                controller = {
                    "name": compat.compat_name if compat else route.controller_name,
                    "prefix": prefix,
                    "api": [],
                    "columns": scan_model_columns(route.model) if route.model else [],
                    "info": {
                        "module": route.module,
                        "resource": route.resource,
                        "type": {
                            "name": route.controller_name,
                            "description": route.summary or route.controller_name,
                        },
                    },
                }
                scope_bucket[module_name].append(controller)

            action_key = _resolve_action_key(route)
            if any(a["id"] == action_key for a in controller["api"]):
                continue

            openapi_meta = path_map.get(route.path, {}).get(route.method.lower(), {})
            controller["api"].append({
                "id": action_key,
                "method": route.method,
                "path": route.path,
                "summary": route.summary or openapi_meta.get("summary"),
                "permission": route.permission,
                "ignoreToken": route.ignore_token,
                "dts": {
                    "parameters": openapi_meta.get("parameters", []),
                    "requestBody": openapi_meta.get("requestBody"),
                    "responses": openapi_meta.get("responses", {}),
                }
            })
            if route.query_meta:
                for api_item in controller["api"]:
                    if api_item["id"] == action_key:
                        api_item["query"] = route.query_meta
                if controller.get("columns"):
                    search_fields = set()
                    for item in route.query_meta.get("fieldEq", []):
                        search_fields.add(item["column"])
                    for item in route.query_meta.get("fieldLike", []):
                        search_fields.add(item["column"])
                    
                    for col in controller["columns"]:
                        if col["propertyName"] in search_fields:
                            col["search"] = {"value": True}
                            if col.get("dict"):
                                col["search"]["component"] = {"name": "el-select"}
        return result

    def export_admin(self) -> dict[str, list[dict[str, Any]]]:
        full = self.export()
        admin_data = full.get("admin", {}) if isinstance(full, dict) else {}
        compat: dict[str, list[dict[str, Any]]] = {}

        for module_name, controllers in admin_data.items():
            for controller in controllers:
                info = controller.get("info", {})
                resource = info.get("resource")
                compat_meta = get_resource_compat(module_name, resource)
                mapped_module = compat_meta.compat_module if compat_meta else module_name
                mapped_prefix = compat_meta.compat_prefix if compat_meta else controller.get("prefix")
                mapped_name = compat_meta.compat_name if compat_meta else str(resource or controller.get("name", "")).replace("/", "_")

                compat.setdefault(mapped_module, [])
                api_items = []
                for api in controller.get("api", []):
                    full_path = api.get("path", "")
                    relative_path = full_path.removeprefix(mapped_prefix) if full_path.startswith(mapped_prefix) else f"/{full_path.rstrip('/').split('/')[-1]}"
                    if not relative_path.startswith("/"):
                        relative_path = f"/{relative_path}"
                    api_items.append(
                        {
                            "name": api.get("id") or relative_path.rsplit("/", 1)[-1],
                            "method": api.get("method"),
                            "path": relative_path,
                        }
                    )

                compat[mapped_module].append(
                    {
                        "name": mapped_name,
                        "prefix": mapped_prefix,
                        "api": api_items,
                        "columns": controller.get("columns", []),
                        "pageQueryOp": _build_page_query_op(controller),
                    }
                )

        if "dict" in compat:
            info_controller = next((item for item in compat["dict"] if item["prefix"] == "/admin/dict/info"), None)
            if info_controller is not None:
                extra_paths = {item["path"] for item in info_controller["api"]}
                if "/types" not in extra_paths:
                    info_controller["api"].append({"name": "types", "method": "GET", "path": "/types"})
                if "/data" not in extra_paths:
                    info_controller["api"].append({"name": "data", "method": "POST", "path": "/data"})

        return compat


def _build_page_query_op(controller: dict[str, Any]) -> dict[str, Any]:
    page_api = next((item for item in controller.get("api", []) if item.get("id") == "page"), None)
    if not page_api:
        return {}
    query = page_api.get("query", {}) or {}
    return {
        "fieldEq": query.get("fieldEq", []),
        "fieldLike": query.get("fieldLike", []),
        "keyWordLikeFields": query.get("keywordLikeFields", []),
    }


def _resolve_action_key(route) -> str:
    tail = route.path.rstrip("/").split("/")[-1]
    if route.source in {"crud", "service"}:
        return tail
    if tail == route.resource:
        return route.method.lower()
    return tail
