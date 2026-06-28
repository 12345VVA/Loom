"""
统一异常输出
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.framework.api.response import FORBIDDEN_CODE, UNAUTHORIZED_CODE, VALIDATION_CODE, error

logger = logging.getLogger("app.exceptions")


def _extract_context(request: Request) -> dict:
    """从 request.state 取请求上下文。

    contextvar（request_id 等）在最外层中间件的 finally 中已被 reset，异常 handler
    位于其外层，因此优先读 request.state。
    """
    current_user = getattr(request.state, "current_user", None)
    return {
        "request_id": getattr(request.state, "request_id", None),
        "path": request.url.path,
        "method": request.method,
        "user_id": getattr(current_user, "id", None),
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        code = _map_status_to_code(exc.status_code)
        return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail), code=code))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first_err = errors[0] if errors else {}
        field = ".".join(str(part) for part in first_err.get("loc", []))
        msg = f"参数错误: {field} {first_err.get('msg', '')}"

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error(msg, code=1001),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # 统一异常日志出口：DEBUG / 非 DEBUG 都记录完整堆栈（日志给开发者排查），
        # 响应体仍按 DEBUG 决定是否暴露明细。
        logger.error(
            "未捕获异常: %s: %s",
            type(exc).__name__,
            exc,
            extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                **_extract_context(request),
            },
            exc_info=exc,
        )
        message = str(exc) if settings.DEBUG else "服务器内部错误"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error(message),
        )


def _map_status_to_code(status_code: int) -> int:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return UNAUTHORIZED_CODE
    if status_code == status.HTTP_403_FORBIDDEN:
        return FORBIDDEN_CODE
    if status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return VALIDATION_CODE
    return status_code
