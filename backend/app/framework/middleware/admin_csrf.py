"""
管理端 Origin/Referer 校验。
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.framework.api.response import FORBIDDEN_CODE, error

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ConfigurationError(RuntimeError):
    """CORS / CSRF 配置违规，启动期校验失败时抛出。"""


def assert_cors_configuration(*, allow_credentials: bool, allow_origins: list[str]) -> None:
    """校验 CORS 配置不违反 spec。

    ``allow_credentials=True`` 时禁止 ``allow_origins`` 包含 ``"*"``：
    浏览器会拒绝带凭证（Cookie/Authorization）的通配符 CORS 响应，
    该组合既是 spec 违规也意味着前端无法正常工作。

    本断言在所有环境（含开发）执行：前端开启 withCredentials 后，"*" 在任何环境
    都无法工作，启动期硬失败优于运行时静默失效。如需本地多端口调试，请在 .env
    显式列出可信来源（参考 backend/.env.example）。

    Raises:
        ConfigurationError: 当 allow_credentials=True 且 allow_origins 含 "*" 时。
    """
    if allow_credentials and "*" in allow_origins:
        raise ConfigurationError(
            "CORS 配置违规：allow_credentials=True 与 allow_origins=['*'] 不能共存"
            "（浏览器会拒绝带凭证的通配符响应）。请显式配置可信来源列表。"
        )


class AdminCsrfOriginMiddleware:
    """对管理端变更请求做可选同源校验。

    纯 ASGI（异步审查 P1-1，样板 operation_log/body_buffer/exception_guard）；
    校验语义与原 BaseHTTPMiddleware 版逐条对齐。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if (
            not settings.ADMIN_CSRF_ORIGIN_CHECK_ENABLED
            or scope["method"] in SAFE_METHODS
            or not scope.get("path", "").startswith("/admin")
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        referer = headers.get("referer")
        source = origin or referer
        if not source:
            await JSONResponse(status_code=403, content=error("缺少来源校验信息", code=FORBIDDEN_CODE))(
                scope, receive, send
            )
            return

        allowed = {_normalize_origin(item) for item in settings.cors_origins_list}
        if "*" in allowed:
            await self.app(scope, receive, send)
            return

        if _normalize_origin(source) not in allowed:
            await JSONResponse(status_code=403, content=error("非法请求来源", code=FORBIDDEN_CODE))(
                scope, receive, send
            )
            return

        await self.app(scope, receive, send)


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"
