"""
全局限流中间件

基于 Redis 原子计数器的固定窗口限流，按客户端 IP + 路由前缀分级限速。
限流检查在业务处理之前执行，超限请求直接返回 429，不进入后续中间件和路由。
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.framework.api.error_codes import ErrorCode
from app.framework.middleware.metrics import record_metric_event
from app.framework.request_utils import get_client_ip
from app.modules.base.service.cache_service import cache_incr

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


def _get_whitelist_paths() -> set[str]:
    return set(p.strip() for p in settings.RATE_LIMIT_WHITELIST_PATHS.split(",") if p.strip())


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局限流中间件：在业务处理前检查频率，超限直接返回 429。"""

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"

        if path in _get_whitelist_paths():
            return await call_next(request)

        limit = _resolve_limit(path)
        client_id = _get_client_id(request)
        window = int(time.time()) // 60
        cache_key = f"ratelimit:{client_id}:{window}:{path}"

        current = cache_incr(cache_key, ttl_seconds=90)

        if current is None:
            # Redis 计数不可靠：fail-open 放行，跳过限流判断（避免不可靠计数误拒正常请求）
            logger.warning("限流计数不可靠（Redis 异常），client_id=%s path=%s 本次放行", client_id, path)
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            return response
        if current > limit:
            logger.warning("限流触发: client_id=%s path=%s limit=%d", client_id, path, limit)
            record_metric_event("rate_limited", path=path)
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
