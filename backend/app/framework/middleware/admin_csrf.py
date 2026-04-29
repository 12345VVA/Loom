"""
管理端 Origin/Referer 校验。
"""
from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.framework.api.response import FORBIDDEN_CODE, error

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class AdminCsrfOriginMiddleware(BaseHTTPMiddleware):
    """对管理端变更请求做可选同源校验。"""

    async def dispatch(self, request: Request, call_next):
        if (
            not settings.ADMIN_CSRF_ORIGIN_CHECK_ENABLED
            or request.method in SAFE_METHODS
            or not request.url.path.startswith("/admin")
        ):
            return await call_next(request)

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or referer
        if not source:
            return JSONResponse(status_code=403, content=error("缺少来源校验信息", code=FORBIDDEN_CODE))

        allowed = {_normalize_origin(item) for item in settings.cors_origins_list}
        if "*" in allowed:
            return await call_next(request)

        if _normalize_origin(source) not in allowed:
            return JSONResponse(status_code=403, content=error("非法请求来源", code=FORBIDDEN_CODE))

        return await call_next(request)


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"
