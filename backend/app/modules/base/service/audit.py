"""操作日志写入（base 向框架注册的审计实现）。

framework/middleware/operation_log.py 经 DI（registry "audit_write"）调用，
SysLog ORM 依赖收敛于 base 模块内——框架层不再感知具体日志表。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session

from app.core.database import engine
from app.modules.base.model.sys import SysLog

logger = logging.getLogger(__name__)


def write_operation_log(payload: dict[str, Any]) -> None:
    """将操作日志 payload 落库（失败仅记录，不影响主流程）。"""
    try:
        with Session(engine) as session:
            log = SysLog(**payload)
            session.add(log)
            session.commit()
    except Exception as exc:
        logger.error(
            "操作日志写入失败 - path: %s, method: %s, user_id: %s",
            payload.get("action"),
            payload.get("method"),
            payload.get("user_id"),
            exc_info=exc,
        )
