"""
Cool 风格响应包装
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

SUCCESS_CODE = 1000
FAIL_CODE = 1001
UNAUTHORIZED_CODE = 1002
FORBIDDEN_CODE = 1003
VALIDATION_CODE = 1004


def ok(data: Any = None, message: str = "success", code: int = SUCCESS_CODE) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": normalize_data(data),
    }


def page_result(*, items: list[Any], total: int, page: int, size: int) -> dict[str, Any]:
    return {
        "list": normalize_data(items),
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
        },
    }


def error(message: str, *, code: int = FAIL_CODE, data: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": normalize_data(data),
    }


def is_enveloped(payload: Any) -> bool:
    return isinstance(payload, dict) and {"code", "message", "data"}.issubset(payload.keys())


def normalize_data(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, BaseModel):
        return normalize_data(data.model_dump(mode="json"))
    if is_dataclass(data):
        return normalize_data(asdict(data))
    if isinstance(data, dict):
        return {key: normalize_data(value) for key, value in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [normalize_data(item) for item in data]
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, (datetime, date)):
        return data.isoformat()
    if isinstance(data, Decimal):
        return float(data)
    return data
