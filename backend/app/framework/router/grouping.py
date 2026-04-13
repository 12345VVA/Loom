"""
模块约定式路由配置与构建工具
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class RouteGroupConfig:
    """路由分组配置"""

    name: str
    prefix: str
    auth_required: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


def get_group_config(group_name: str) -> RouteGroupConfig:
    """按作用域读取默认分组配置"""
    defaults = {
        "admin": RouteGroupConfig(
            name="admin",
            prefix="/admin",
            auth_required=True,
            tags=("admin",),
        ),
        "aiapi": RouteGroupConfig(
            name="aiapi",
            prefix="/aiapi",
            auth_required=True,
            tags=("aiapi",),
        ),
        "app": RouteGroupConfig(
            name="app",
            prefix="/app",
            auth_required=True,
            tags=("app",),
        ),
        "public": RouteGroupConfig(
            name="public",
            prefix="",
            auth_required=False,
            tags=("public",),
        ),
    }
    return defaults.get(group_name, RouteGroupConfig(name=group_name, prefix=f"/{group_name}"))


def build_group_router(
    group_name: str,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
) -> APIRouter:
    """根据作用域构建 APIRouter"""
    group_config = get_group_config(group_name)
    merged_tags = list(group_config.tags)
    if tags:
        merged_tags.extend(tags)

    return APIRouter(
        prefix=prefix,
        tags=merged_tags,
    )


def build_module_router(
    group_name: str,
    *,
    tags: list[str] | None = None,
) -> APIRouter:
    """构建模块约定式 APIRouter，不直接声明前缀"""
    return build_group_router(group_name, prefix="", tags=tags)
