"""
模块运行时中间件桥接
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware


class PrefixScopedMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, middleware_cls: type[BaseHTTPMiddleware], prefixes: tuple[str, ...], module_name: str):
        super().__init__(app)
        self._middleware = middleware_cls(app)
        self._prefixes = tuple(prefix.rstrip("/") or "/" for prefix in prefixes)
        self._module_name = module_name

    async def dispatch(self, request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if not any(path.startswith(prefix) for prefix in self._prefixes):
            return await call_next(request)
        request.state.module_name = self._module_name
        return await self._middleware.dispatch(request, call_next)
