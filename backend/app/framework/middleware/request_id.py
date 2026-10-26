"""
请求 ID 中间件。
"""

from __future__ import annotations

from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx, request_method_ctx, request_path_ctx


def _header_value(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


class RequestIdMiddleware:
    """为每个请求生成或透传 X-Request-Id。

    纯 ASGI（异步审查 P1-1）：BaseHTTPMiddleware 的每请求 task-group + 流转发封装
    在 SSE 场景下要维护整条 cancel scope 链，本项目纯 ASGI 样板见 operation_log /
    body_buffer / exception_guard。契约保持不变：
    - ``request.state.request_id``（500 追踪号依赖，error_contract）——经 scope["state"]
      传递（Starlette Request.state 底层即该 dict）；
    - 请求 ID / 路径 / 方法三个日志 contextvar 的 set/reset；
    - 响应头 X-Request-Id。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header_value(scope, b"x-request-id") or uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token_id = request_id_ctx.set(request_id)
        token_path = request_path_ctx.set(scope.get("path", ""))
        token_method = request_method_ctx.set(scope.get("method", ""))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(token_id)
            request_path_ctx.reset(token_path)
            request_method_ctx.reset(token_method)
