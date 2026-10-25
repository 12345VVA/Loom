"""
统一异常输出
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.framework.api.error_codes import ErrorCode, status_to_error_code
from app.framework.api.response import error

logger = logging.getLogger("app.exceptions")

# 4xx 客户端错误分级日志：认证/授权/限流失败对安全排查有价值（WARNING），
# 404 路由探测类噪音大（DEBUG），其余 INFO
_CLIENT_ERROR_LOG_LEVELS = {401: logging.WARNING, 403: logging.WARNING, 429: logging.WARNING, 404: logging.DEBUG}


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
    # 注册 StarletteHTTPException（而非 fastapi.HTTPException 子类）：路由不存在
    # (404) / 方法不允许 (405) 由 starlette Router 抛父类异常，注册子类永远接不到，
    # 会落回 FastAPI 内置 handler 返回裸 {"detail": ...}（再被响应包装误包成
    # code=1000 success）。父类注册同时覆盖 fastapi.HTTPException。
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        level = _CLIENT_ERROR_LOG_LEVELS.get(exc.status_code, logging.INFO)
        if level >= logging.INFO:
            logger.log(
                level,
                "HTTP %s: %s",
                exc.status_code,
                exc.detail,
                extra=_extract_context(request),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error(str(exc.detail), code=status_to_error_code(exc.status_code)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        # loc 形如 ("query", "a") / ("body", "items", 0, "name")——首段是参数位置，
        # 对用户无意义，展示从字段名开始
        details = [
            {
                "field": ".".join(str(part) for part in item.get("loc", [])[1:]) or str(item.get("loc", [""])[0]),
                "message": item.get("msg", ""),
            }
            for item in errors
        ]
        first = details[0] if details else {"field": "", "message": ""}
        logger.warning(
            "参数校验失败: %s %s（%d 处）",
            first["field"],
            first["message"],
            len(details),
            extra=_extract_context(request),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error(
                f"参数错误: {first['field']} {first['message']}",
                code=ErrorCode.VALIDATION,
                data={"errors": details} if len(details) > 1 else None,
            ),
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
        request_id = getattr(request.state, "request_id", None)
        if settings.DEBUG:
            message = str(exc)
        else:
            # 500 响应体带追踪号：用户截图报障可与 error.log 精确对账
            message = f"服务器内部错误（追踪号 {request_id}）" if request_id else "服务器内部错误"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error(message),
        )
