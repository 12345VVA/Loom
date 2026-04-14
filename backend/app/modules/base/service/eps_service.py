"""
EPS 服务扫描导出
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

import re
from app.framework.controller_meta import get_registered_exported_routes
from app.framework.eps.scanner import scan_model_columns
from app.modules.base.compat import get_resource_compat


def _fix_dts_types(data: Any) -> Any:
    """递归修复 OpenAPI 中的类型，将 integer 替换为 number"""
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "type" and v == "integer":
                new_data[k] = "number"
            elif k == "type" and v == "array" and "items" in data:
                # 处理数组类型中的 items
                new_data[k] = v
            else:
                new_data[k] = _fix_dts_types(v)
        return new_data
    elif isinstance(data, list):
        return [_fix_dts_types(item) for item in data]
    return data


class EpsService:
    def __init__(self, app: FastAPI):
        self.app = app

    def export(self) -> dict[str, list[dict[str, Any]]]:
        openapi = self.app.openapi()
        path_map = openapi.get("paths", {})
        result: dict[str, list[dict[str, Any]]] = {}

        entities: dict[tuple[str, str], dict[str, Any]] = {}

        for route in get_registered_exported_routes():
            if route.scope != "admin":
                continue

            compat = get_resource_compat(route.module, route.resource)
            mapped_module = compat.compat_module if compat else route.module
            mapped_name = compat.compat_name if compat else str(route.resource).split("/")[-1]
            
            # 解决命名冲突：对于非 base 模块的通用名称（info, type, data, log），增加模块名前缀
            if mapped_name in ("info", "type", "data", "log") and mapped_module not in ("base",):
                 # 转换为首字母大写拼接，例如 TaskInfo, DictInfo
                 mapped_name = mapped_module.capitalize() + mapped_name.capitalize()
                 
            mapped_prefix = compat.compat_prefix if compat else f"/{route.scope}/{route.module}/{route.resource}"
            namespace = mapped_prefix.lstrip("/")
            key = (mapped_module, mapped_prefix)

            entity = entities.get(key)
            if entity is None:
                columns = scan_model_columns(route.model) if route.model else []
                entity = {
                    "module": mapped_module,
                    "name": mapped_name,
                    "prefix": mapped_prefix,
                    "namespace": namespace,
                    "api": [],
                    "columns": columns,
                    "pageColumns": [dict(item) for item in columns],
                    "pageQueryOp": {
                        "fieldEq": [],
                        "fieldLike": [],
                        "keyWordLikeFields": [],
                    },
                }
                entities[key] = entity

            action_name = _resolve_action_name(route)
            relative_path = _to_relative_path(mapped_prefix, route.path)
            openapi_meta = path_map.get(route.path, {}).get(route.method.lower(), {})
            if any(item["name"] == action_name and item["path"] == relative_path for item in entity["api"]):
                continue

            entity["api"].append(
                {
                    "name": action_name,
                    "method": route.method,
                    "path": relative_path,
                    "prefix": mapped_prefix,
                    "summary": route.summary or openapi_meta.get("summary") or action_name,
                    "tag": mapped_name,
                    "dts": {
                        "parameters": _fix_dts_types(openapi_meta.get("parameters", [])),
                        "requestBody": _fix_dts_types(openapi_meta.get("requestBody")),
                        "responses": _fix_dts_types(openapi_meta.get("responses", {})),
                    },
                }
            )

            if route.query_meta and action_name == "page":
                entity["pageQueryOp"] = _build_page_query_op(route.query_meta)
                _mark_search_columns(entity["columns"], entity["pageQueryOp"])
                entity["pageColumns"] = [dict(item) for item in entity["columns"]]

        for entity in entities.values():
            result.setdefault(entity["module"], []).append(entity)

        for module_entities in result.values():
            module_entities.sort(key=lambda item: item["prefix"])
            for entity in module_entities:
                entity["api"].sort(key=lambda item: (item["path"], item["method"]))

        return result

    def export_admin(self) -> dict[str, list[dict[str, Any]]]:
        return self.export()


def _resolve_action_name(route) -> str:
    tail = route.path.rstrip("/").split("/")[-1]
    if route.source in {"crud", "service"}:
        return tail
    if tail == route.resource:
        return route.method.lower()
    return tail


def _to_relative_path(prefix: str, full_path: str) -> str:
    normalized_prefix = prefix.rstrip("/")
    normalized_full = full_path.rstrip("/")
    if normalized_full.startswith(normalized_prefix):
        suffix = normalized_full[len(normalized_prefix) :]
        if not suffix:
            return "/"
        return suffix if suffix.startswith("/") else f"/{suffix}"
    tail = normalized_full.split("/")[-1]
    return f"/{tail}" if tail else "/"


def _build_page_query_op(query_meta: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "fieldEq": [
            item.get("requestParam") or item.get("column")
            for item in query_meta.get("fieldEq", [])
            if item.get("requestParam") or item.get("column")
        ],
        "fieldLike": [
            item.get("requestParam") or item.get("column")
            for item in query_meta.get("fieldLike", [])
            if item.get("requestParam") or item.get("column")
        ],
        "keyWordLikeFields": list(query_meta.get("keywordLikeFields", [])),
    }


def _mark_search_columns(columns: list[dict[str, Any]], page_query_op: dict[str, list[str]]) -> None:
    search_sources = set(page_query_op.get("fieldEq", [])) | set(page_query_op.get("fieldLike", [])) | set(
        page_query_op.get("keyWordLikeFields", [])
    )
    if not search_sources:
        return
    for column in columns:
        source = column.get("source") or column.get("propertyName")
        if source in search_sources:
            column["search"] = {"value": True}
