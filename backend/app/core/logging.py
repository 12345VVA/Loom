"""
应用日志配置。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import traceback
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
request_path_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_path", default=None)
request_method_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_method", default=None)
current_user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)
# 工作流实例关联：评估按 instance 精确聚合 token/cost 时，由 runtime_service._log_call 读取
workflow_instance_id_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "workflow_instance_id", default=None
)
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


# 控制台 traceback 过滤：跳过这些第三方框架的内部帧，让堆栈聚焦业务代码。
# filename 统一成正斜杠后再做子串匹配，兼容 Windows 路径分隔符。
_FRAME_FILTER_SUBSTRINGS: tuple[str, ...] = (
    "starlette/middleware/base.py",
    "starlette/middleware/errors.py",
    "starlette/_exception_handler.py",
    "starlette/exceptions.py",
    "anyio/",
    "uvicorn/protocols/",
    "uvicorn/middleware/",
)


def _frame_is_framework(frame) -> bool:
    """判断单帧是否属于需过滤的第三方框架内部帧。"""
    return any(sub in (frame.filename or "").replace("\\", "/") for sub in _FRAME_FILTER_SUBSTRINGS)


def _append_filtered_traceback(te: traceback.TracebackException, lines: list[str]) -> None:
    """递归渲染 TracebackException：过滤每段的框架内部帧，并保留异常链（__cause__/__context__）。

    渲染顺序与标准 traceback.format_exception 一致：先 cause/context，再分隔句，最后当前异常。
    """
    if te.__cause__:
        _append_filtered_traceback(te.__cause__, lines)
        lines.append("")
        lines.append("The above exception was the direct cause of the following exception:")
        lines.append("")
    elif te.__context__ and not te.__suppress_context__:
        _append_filtered_traceback(te.__context__, lines)
        lines.append("")
        lines.append("During handling of the above exception, another exception occurred:")
        lines.append("")
    lines.append("Traceback (most recent call last):")
    for frame in te.stack:
        if _frame_is_framework(frame):
            continue
        lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}')
        if frame.line:
            lines.append(f"    {frame.line}")
    lines.extend(line.rstrip("\n") for line in te.format_exception_only())


def _format_filtered_traceback(exc_info) -> str:
    """格式化异常堆栈：过滤第三方框架内部帧，并保留异常链根因。

    渲染异常时回退标准完整堆栈，避免误伤。
    """
    etype, value, tb = exc_info
    lines: list[str] = []
    _append_filtered_traceback(traceback.TracebackException.from_exception(value), lines)
    text = "\n".join(lines).rstrip("\n")
    if text:
        return text
    return "".join(traceback.format_exception(etype, value, tb)).rstrip("\n")


class ConsoleFormatter(logging.Formatter):
    """人类可读的多行控制台 formatter。

    - 行首：时间 级别 logger 消息
    - 上下文：request_id / user_id / method / path（来自 contextvar）
    - extra 字段：业务附加字段（与 JsonFormatter 同源）
    - 多行 traceback：过滤框架内部帧，业务帧靠前可见

    文件侧仍使用 JsonFormatter 以保留结构化检索能力。
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        parts = [f"{ts} {record.levelname:<7} [{record.name}] {record.getMessage()}"]

        ctx_parts = []
        for label, value in {
            "rid": request_id_ctx.get(),
            "user": current_user_id_ctx.get(),
            "verb": request_method_ctx.get(),
            "path": request_path_ctx.get(),
        }.items():
            if value is not None:
                ctx_parts.append(f"{label}={value}")
        if ctx_parts:
            parts.append("  " + " ".join(ctx_parts))

        extra_items = []
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_KEYS or key.startswith("_"):
                continue
            extra_items.append(f"{key}={value}")
        if extra_items:
            parts.append("  " + " ".join(extra_items))

        if record.exc_info:
            parts.append(_format_filtered_traceback(record.exc_info))
        if record.stack_info:
            parts.append(self.formatStack(record.stack_info))
        return "\n".join(parts)


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
    "app.log": None,  # 全量日志
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


def _ensure_utf8_stderr() -> None:
    """确保控制台 stderr 以 UTF-8 输出。

    Windows 默认 stderr 编码常为 cp936(GBK)，当日志含 emoji/生僻字等字符时会触发
    UnicodeEncodeError，导致日志写入失败（logging 仅在内部 handleError 吞掉，日志丢失）。
    reconfigure 为 UTF-8；环境不支持时（stderr 被重定向等）静默跳过。
    """
    stream = sys.stderr
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if encoding == "utf8":
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass


def configure_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    retention_days: int = 30,
    file_prefix: str = "",
) -> None:
    _ensure_utf8_stderr()
    json_formatter = JsonFormatter()
    console_formatter = ConsoleFormatter()
    root = logging.getLogger()
    root.handlers.clear()

    level = getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(level)

    # 控制台输出：人类可读的多行文本
    console = logging.StreamHandler()
    console.setFormatter(console_formatter)
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
        handler.setFormatter(json_formatter)
        if min_level is not None:
            handler.addFilter(_MinLevelFilter(min_level))
        root.addHandler(handler)

    # 第三方库日志级别封顶
    for name, ceiling in _THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(name).setLevel(max(level, ceiling))
