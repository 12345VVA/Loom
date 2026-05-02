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
