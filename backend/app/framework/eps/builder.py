"""
EPS (Entity Protocol Specification) 数据构建器
"""
from __future__ import annotations

from typing import Any
from fastapi import FastAPI

from app.framework.controller_meta import get_registered_exported_routes


def build_eps_data(app: FastAPI) -> dict[str, Any]:
    """
    根据已注册的路由元数据构建 EPS 树结构。
    结构为: { module: { resource: { action: { method, path, summary ... } } } }
    """
    routes = get_registered_exported_routes()
    tree: dict[str, Any] = {}

    for route in routes:
        # 只处理管理端 scope
        if route.scope != "admin":
            continue

        module = route.module
        resource = route.resource
        
        if module not in tree:
            tree[module] = {}
        
        module_node = tree[module]
        
        # 资源层级转换：将 base:user 这种资源名拆解为层级对象
        # 对应 Loom 的 service.base.user.page()
        normalized_resource = str(resource).replace("/", ":").replace(".", ":")
        resource_parts = [part for part in normalized_resource.split(":") if part]
        current_node = module_node
        for part in resource_parts:
            if part not in current_node:
                current_node[part] = {}
            current_node = current_node[part]
        
        # 提取 Action 名称（路径最后一段）
        # e.g. /admin/base/sys/user/page -> page
        # 或者从 path 提取
        action_name = route.path.rstrip("/").split("/")[-1]
        
        # 存入 API 定义
        current_node[action_name] = {
            "method": route.method,
            "path": route.path,
            "summary": route.summary,
            "permission": route.permission,
            "dts": {
                "parameters": [], # 简化实现，暂不导出详细参数类型
                "responses": {}
            }
        }
        
        # 如果是 CRUD 生成的，附带查询元数据
        if route.query_meta:
            current_node[action_name]["query"] = route.query_meta

    return tree
