"""
路由标签与元数据
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Match


CLASS_TAGS_ATTR = "__cool_class_tags__"
METHOD_TAGS_ATTR = "__cool_method_tags__"
ROUTE_META_ATTR = "__cool_route_meta__"
PERMISSION_ATTR = "__required_permission__"


class TagTypes:
    """内置 URL 标签"""

    IGNORE_TOKEN = "IGNORE_TOKEN"
    IGNORE_PERMISSION = "IGNORE_PERMISSION"
    IGNORE_LOG = "IGNORE_LOG"
    SCOPE = "SCOPE"


@dataclass(frozen=True)
class CoolRouteMeta:
    """自定义控制器方法路由元数据"""

    method: str
    path: str
    summary: str | None = None
    permission: str | None = None
    role_codes: tuple[str, ...] = field(default_factory=lambda: ("admin",))
    tags: tuple[str, ...] = field(default_factory=tuple)
    anonymous: bool = False


def cool_url_tag(*tags: str):
    """为方法或类标记 URL 标签。"""

    def decorator(target):
        attr = CLASS_TAGS_ATTR if isinstance(target, type) else METHOD_TAGS_ATTR
        existing = list(getattr(target, attr, ()))
        for tag in tags:
            if tag not in existing:
                existing.append(tag)
        setattr(target, attr, tuple(existing))
        return target

    return decorator


def cool_tag(tag: str):
    """为方法标记单个标签。"""
    return cool_url_tag(tag)


def allow_anonymous(func: Callable):
    """兼容匿名接口声明。"""
    return cool_tag(TagTypes.IGNORE_TOKEN)(func)


def permission_required(permission: str):
    """兼容权限点声明。"""

    def decorator(func: Callable):
        setattr(func, PERMISSION_ATTR, permission)
        return func

    return decorator


def route(
    method: str,
    path: str,
    *,
    summary: str | None = None,
    permission: str | None = None,
    role_codes: tuple[str, ...] = ("admin",),
    tags: tuple[str, ...] = (),
    anonymous: bool = False,
):
    """为类控制器方法声明路由元数据。"""

    def decorator(func: Callable):
        setattr(
            func,
            ROUTE_META_ATTR,
            CoolRouteMeta(
                method=method.upper(),
                path=path,
                summary=summary,
                permission=permission,
                role_codes=role_codes,
                tags=tags,
                anonymous=anonymous,
            ),
        )
        if permission:
            setattr(func, PERMISSION_ATTR, permission)
        if anonymous:
            cool_tag(TagTypes.IGNORE_TOKEN)(func)
        for tag in tags:
            cool_tag(tag)(func)
        return func

    return decorator


def Get(path: str, **kwargs):
    return route("GET", path, **kwargs)


def Post(path: str, **kwargs):
    return route("POST", path, **kwargs)


def get_permission_meta(func: Callable) -> str | None:
    target = getattr(func, "__func__", func)
    return getattr(target, PERMISSION_ATTR, None)


def get_route_meta(func: Callable) -> CoolRouteMeta | None:
    target = getattr(func, "__func__", func)
    return getattr(target, ROUTE_META_ATTR, None)


def get_route_tags(func: Callable) -> set[str]:
    target = getattr(func, "__func__", func)
    method_tags = set(getattr(target, METHOD_TAGS_ATTR, ()))
    bound_self = getattr(func, "__self__", None)
    class_tags = set(getattr(bound_self.__class__, CLASS_TAGS_ATTR, ())) if bound_self is not None else set()
    return class_tags | method_tags


def get_scope_tag(func: Callable) -> str | None:
    for tag in get_route_tags(func):
        if tag.startswith(f"{TagTypes.SCOPE}:"):
            return tag.split(":", 1)[1]
    return None


def resolve_request_route(app: FastAPI, scope: dict[str, Any]) -> APIRoute | None:
    """解析请求命中的 APIRoute。"""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    return None
