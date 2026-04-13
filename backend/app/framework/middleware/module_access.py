"""
模块级访问上下文中间件
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware


class ModuleAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.module_accessed = True
        return await call_next(request)
