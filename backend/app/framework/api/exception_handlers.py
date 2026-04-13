"""
统一异常输出
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.framework.api.response import FORBIDDEN_CODE, UNAUTHORIZED_CODE, VALIDATION_CODE, error


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
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        if settings.DEBUG:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=error(str(exc)),
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error("服务器内部错误"),
        )


def _map_status_to_code(status_code: int) -> int:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return UNAUTHORIZED_CODE
    if status_code == status.HTTP_403_FORBIDDEN:
        return FORBIDDEN_CODE
    if status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return VALIDATION_CODE
    return status_code
