"""
请求 ID 中间件。
"""
from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.logging import request_id_ctx, request_method_ctx, request_path_ctx


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或透传 X-Request-Id。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        token_id = request_id_ctx.set(request_id)
        token_path = request_path_ctx.set(request.url.path)
        token_method = request_method_ctx.set(request.method)
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            request_id_ctx.reset(token_id)
            request_path_ctx.reset(token_path)
            request_method_ctx.reset(token_method)
