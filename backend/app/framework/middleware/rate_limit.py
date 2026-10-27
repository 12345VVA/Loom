"""
全局限流中间件

基于 Redis 原子计数器的固定窗口限流，按客户端 IP + 路由前缀分级限速。
限流检查在业务处理之前执行，超限请求直接返回 429，不进入后续中间件和路由。
计数桶取路由模板（评审 F1）：完整请求路径做桶会被实例级路径与 /uploads 文件名
遍历线性放大计数维度，限流实质失效。
"""

from __future__ import annotations

import asyncio
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match

from app.core.config import settings
from app.framework.api.error_codes import ErrorCode
from app.framework.middleware.metrics import record_metric_event
from app.framework.request_utils import get_client_ip
from app.framework.runtime import registry

logger = logging.getLogger(__name__)

_PREFIX_LIMITS: list[tuple[str, int]] = []


def _build_prefix_limits() -> list[tuple[str, int]]:
    if _PREFIX_LIMITS:
        return _PREFIX_LIMITS
    _PREFIX_LIMITS.extend(
        sorted(
            [
                ("/admin/base/open", settings.RATE_LIMIT_OPEN),
                ("/admin", settings.RATE_LIMIT_ADMIN),
                ("/app", settings.RATE_LIMIT_DEFAULT),
                ("/aiapi", settings.RATE_LIMIT_DEFAULT),
            ],
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
    )
    return _PREFIX_LIMITS


_WHITELIST_PATHS: set[str] = set()


def _get_whitelist_paths() -> set[str]:
    if not _WHITELIST_PATHS:
        _WHITELIST_PATHS.update(p.strip() for p in settings.RATE_LIMIT_WHITELIST_PATHS.split(",") if p.strip())
    return _WHITELIST_PATHS


def _resolve_limit(path: str) -> int:
    for prefix, limit in _build_prefix_limits():
        if path.startswith(prefix):
            return limit
    return settings.RATE_LIMIT_DEFAULT


def _get_client_ip(request: Request) -> str:
    """
    解析真实客户端 IP。

    薄包装：委托给共享实现 `app.framework.request_utils.get_client_ip`，
    保留模块内调用习惯与返回值（"unknown" 兜底）。

    安全策略见 `get_client_ip` 文档。
    """
    return get_client_ip(request)


def _get_client_id(request: Request) -> str:
    import hashlib

    token = request.headers.get("authorization")
    if token and token.startswith("Bearer "):
        token_hash = hashlib.md5(token.encode()).hexdigest()
        return f"user:{token_hash}"
    ip = _get_client_ip(request)
    return f"ip:{ip}"


# ---- 计数桶解析（评审 F1）：完整请求路径 → 路由模板 ----
# 限流先于路由执行，scope["route"] 尚不存在（Router 在 call_next 内部匹配后才写入；
# metrics 是在响应期读所以能用），须按 APIRoute.matches 自行解析。首请求惰性收集
# 路由表（保持注册顺序——API_VERSION_PREFIX 双挂载时首个 FULL 匹配须与 FastAPI
# 实际路由一致）；命中结果进有界缓存，未命中（404/405 探测）回退截断 path 且不入
# 缓存（同一 path 换 method 可能转为 FULL，缓存会毒化）。
_ROUTE_TABLE: list = []
_ROUTES_APP_ID: int | None = None
_TEMPLATE_CACHE: dict[str, str] = {}
_TEMPLATE_CACHE_MAX = 4096
_UPLOADS_ROUTE_PATH = "/uploads/{file_path:path}"
_UPLOADS_BUCKET = "/uploads"


def _collect_routes(app) -> None:
    """惰性收集 APIRoute；按 app 身份失效（测试会换 app，生产单 app 不触发重建）。"""
    global _ROUTES_APP_ID
    app_id = id(app)
    if _ROUTES_APP_ID == app_id and _ROUTE_TABLE:
        return
    from fastapi.routing import APIRoute

    _ROUTE_TABLE[:] = [route for route in app.routes if isinstance(route, APIRoute)]
    _TEMPLATE_CACHE.clear()
    _ROUTES_APP_ID = app_id


def _reset_rate_limit_caches() -> None:
    """测试辅助：清空全部分级/路由/模板惰性缓存。

    _PREFIX_LIMITS 首次调用即按当时 settings 冻结（生产语义），测试逐用例 patch
    settings 后必须强制重建，否则前一个用例的限额会泄漏到后续用例（429 串扰）。
    """
    global _ROUTES_APP_ID
    _PREFIX_LIMITS.clear()
    _ROUTE_TABLE.clear()
    _TEMPLATE_CACHE.clear()
    _ROUTES_APP_ID = None


def _resolve_bucket(scope) -> str:
    """请求 scope → 限流计数桶。

    路由命中取模板（/app/workflow/instances/{id}/... 收敛为单桶）；/uploads 聚合为
    固定桶（换文件名不放大计数维度）；未命中回退截断 path（与 metrics 未匹配口径一致）。
    """
    path = scope.get("path", "")
    cached = _TEMPLATE_CACHE.get(path)
    if cached is not None:
        return cached
    app = scope.get("app")
    if app is not None:
        _collect_routes(app)
        for route in _ROUTE_TABLE:
            match, _child_scope = route.matches(scope)
            if match is Match.FULL:
                template = _UPLOADS_BUCKET if route.path == _UPLOADS_ROUTE_PATH else route.path
                if len(_TEMPLATE_CACHE) < _TEMPLATE_CACHE_MAX:
                    _TEMPLATE_CACHE[path] = template
                return template
    return path[:120]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局限流中间件：在业务处理前检查频率，超限直接返回 429。"""

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"

        if path in _get_whitelist_paths():
            return await call_next(request)

        bucket = _resolve_bucket(request.scope)
        limit = _resolve_limit(bucket)
        client_id = _get_client_id(request)
        window = int(time.time()) // 60
        cache_key = f"ratelimit:{client_id}:{window}:{bucket}"

        # cache_incr 是同步 Redis 网络往返，必须 to_thread 卸载——本中间件在事件循环上
        # 执行，直接调用会让每个请求都阻塞 loop（异步审查 P0-1；framework 禁 import
        # modules，registry 异步化留待后续，先以线程卸载止血）
        current = await asyncio.to_thread(registry.resolve("cache_incr"), cache_key, ttl_seconds=90)

        if current is None:
            # Redis 计数不可靠：fail-open 放行，跳过限流判断（避免不可靠计数误拒正常请求）
            logger.warning("限流计数不可靠（Redis 异常），client_id=%s path=%s 本次放行", client_id, path)
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            return response
        if current > limit:
            logger.warning("限流触发: client_id=%s path=%s bucket=%s limit=%d", client_id, path, bucket, limit)
            record_metric_event("rate_limited", path=bucket)
            return JSONResponse(
                status_code=429,
                content={"code": int(ErrorCode.RATE_LIMITED), "message": "请求过于频繁，请稍后再试", "data": None},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        remaining = max(0, limit - current)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
