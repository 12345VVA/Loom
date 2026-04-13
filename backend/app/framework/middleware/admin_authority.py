"""
多 scope 全局鉴权中间件
"""
from __future__ import annotations

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlmodel import Session

from app.core.database import engine
from app.framework.router.grouping import get_group_config
from app.framework.router.route_meta import TagTypes, get_scope_tag, get_route_tags, resolve_request_route
from app.modules.base.service.authority_service import authorize_request

SUPPORTED_SCOPES = ("admin", "app", "aiapi")


class AdminAuthorityMiddleware(BaseHTTPMiddleware):
    """统一处理 /admin、/app、/aiapi 请求鉴权。"""

    async def dispatch(self, request: Request, call_next):
        scope_name = self._resolve_scope_name(request.url.path.rstrip("/") or "/")
        if scope_name is None:
            return await call_next(request)

        matched_route = resolve_request_route(request.app, request.scope)
        route_tags = get_route_tags(matched_route.endpoint) if matched_route else set()
        route_scope = get_scope_tag(matched_route.endpoint) if matched_route else None
        effective_scope = route_scope or scope_name
        scope_whitelists = getattr(request.app.state, "scope_whitelists", {})
        scope_whitelist = scope_whitelists.get(effective_scope, set())

        try:
            with Session(engine) as session:
                authorize_request(session, request, effective_scope, route_tags, scope_whitelist)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        return await call_next(request)

    def _resolve_scope_name(self, path: str) -> str | None:
        for scope_name in SUPPORTED_SCOPES:
            prefix = get_group_config(scope_name).prefix
            if path.startswith(prefix):
                return scope_name
        return None
