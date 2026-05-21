"""
应用日志配置。
"""
from __future__ import annotations

import json
import logging
import contextvars
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
request_path_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_path", default=None)
request_method_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_method", default=None)
current_user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)
_STANDARD_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        for key, value in {
            "request_id": request_id_ctx.get(),
            "path": request_path_ctx.get(),
            "method": request_method_ctx.get(),
            "user_id": current_user_id_ctx.get(),
        }.items():
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_THIRD_PARTY_LOG_LEVELS: dict[str, int] = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
    "uvicorn.access": logging.WARNING,
    "celery.redirected": logging.WARNING,
    "filelock": logging.WARNING,
}

# 文件 → 最低级别（None 表示跟随根级别）
_LOG_FILES: dict[str, int | None] = {
    "app.log": None,            # 全量日志
    "error.log": logging.ERROR,  # 仅 ERROR/CRITICAL
}


class _MinLevelFilter(logging.Filter):
    """只允许 >= 指定级别的日志记录通过"""
    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Windows 多进程环境下安全滚动的 TimedRotatingFileHandler。
    在重命名锁定时捕获 PermissionError/OSError 并打印警告，防止异常导致日志处理输出大面积 traceback，
    随后安全重新打开原文件流以继续写入。
    """
    def doRollover(self) -> None:
        try:
            super().doRollover()
        except (PermissionError, OSError) as e:
            # 日志轮转异常发生时，使用常规 logger 可能会导致递归循环报错，因此退推至标准错误输出
            print(f"[Logging Warning] Failed to rollover log file: {e}. Reopening stream.", file=sys.stderr)
            try:
                if self.stream and not getattr(self.stream, "closed", True):
                    self.stream.close()
            except Exception:
                pass
            self.stream = self._open()


def configure_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    retention_days: int = 30,
    file_prefix: str = "",
) -> None:
    formatter = JsonFormatter()
    root = logging.getLogger()
    root.handlers.clear()

    level = getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(level)

    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # 按天轮转的文件输出
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    prefix = f"{file_prefix}_" if file_prefix else ""
    for filename, min_level in _LOG_FILES.items():
        handler = SafeTimedRotatingFileHandler(
            str(log_path / f"{prefix}{filename}"),
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        if min_level is not None:
            handler.addFilter(_MinLevelFilter(min_level))
        root.addHandler(handler)

    # 第三方库日志级别封顶
    for name, ceiling in _THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(name).setLevel(max(level, ceiling))
