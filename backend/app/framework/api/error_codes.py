"""
统一错误码定义。
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 1000
    FAIL = 1001
    UNAUTHORIZED = 1002
    FORBIDDEN = 1003
    VALIDATION = 1004
    NOT_FOUND = 1005
    CONFLICT = 1006
    RATE_LIMITED = 1007
    CONFIG_INVALID = 1100
    TASK_FAILED = 1200
    SERVER_ERROR = 1050  # 服务端内部错误（与 4xx 的 FAIL 区分，前端可按码识别 500 类）


# HTTP 状态码 → 业务错误码。未命中的 4xx 落 FAIL、5xx 落 SERVER_ERROR，避免
# "code=404 这类裸状态码混进业务码段" 的契约漂移（历史 fallback 行为）。
_STATUS_TO_ERROR_CODE: dict[int, int] = {
    400: ErrorCode.VALIDATION,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.FAIL,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.VALIDATION,
    422: ErrorCode.VALIDATION,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.SERVER_ERROR,
}


def status_to_error_code(status_code: int) -> int:
    """HTTP 状态码映射业务错误码：已知映射优先，未知 5xx 落 SERVER_ERROR、其余 FAIL。"""
    mapped = _STATUS_TO_ERROR_CODE.get(status_code)
    if mapped is not None:
        return mapped
    return ErrorCode.SERVER_ERROR if status_code >= 500 else ErrorCode.FAIL
