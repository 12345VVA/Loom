"""
按 scope 拆分的鉴权中间件
"""
from __future__ import annotations

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlmodel import Session

from app.core.database import engine
from app.framework.api.response import FORBIDDEN_CODE, UNAUTHORIZED_CODE, error
from app.framework.router.grouping import get_group_config
from app.framework.router.route_meta import get_route_tags, get_scope_tag, resolve_request_route
from app.modules.base.service.authority_service import authorize_request


class ScopeAuthorityMiddleware(BaseHTTPMiddleware):
    scope_name: str = ""

    async def dispatch(self, request: Request, call_next):
        # 允许所有 OPTIONS 请求通过，以支持 CORS 预检
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        prefix = get_group_config(self.scope_name).prefix
        if not path.startswith(prefix):
            return await call_next(request)

        matched_route = resolve_request_route(request.app, request.scope)
        route_tags = get_route_tags(matched_route.endpoint) if matched_route else set()
        route_scope = get_scope_tag(matched_route.endpoint) if matched_route else None
        effective_scope = route_scope or self.scope_name
        scope_whitelists = getattr(request.app.state, "scope_whitelists", {})
        scope_whitelist = scope_whitelists.get(effective_scope, set())

        try:
            with Session(engine) as session:
                authorize_request(session, request, effective_scope, route_tags, scope_whitelist, matched_route)
        except HTTPException as exc:
            code = UNAUTHORIZED_CODE if exc.status_code == 401 else FORBIDDEN_CODE if exc.status_code == 403 else exc.status_code
            return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail), code=code))

        return await call_next(request)


class AdminAuthorityMiddleware(ScopeAuthorityMiddleware):
    scope_name = "admin"


class AppAuthorityMiddleware(ScopeAuthorityMiddleware):
    scope_name = "app"


class AiApiAuthorityMiddleware(ScopeAuthorityMiddleware):
    scope_name = "aiapi"
