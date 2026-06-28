"""日志格式化器单元测试。

覆盖改动 C：控制台多行文本 + 框架帧过滤（保留异常链），文件侧保持 JSON。
"""

from __future__ import annotations

import json
import logging
import sys
import traceback

from app.core import logging as app_logging
from app.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    _format_filtered_traceback,
    _frame_is_framework,
    request_id_ctx,
)


def test_frame_is_framework_flags_known_packages():
    """_frame_is_framework 应识别 starlette/anyio/uvicorn 等框架内部帧，且兼容 Windows 路径。"""
    assert _frame_is_framework(traceback.FrameSummary("site-packages/starlette/middleware/base.py", 40, "dispatch"))
    assert _frame_is_framework(traceback.FrameSummary("site-packages\\anyio\\_taskgroups.py", 10, "run"))
    assert _frame_is_framework(traceback.FrameSummary("x/uvicorn/protocols/http.py", 1, "f"))
    assert not _frame_is_framework(traceback.FrameSummary("app/modules/ai/service/runtime_service.py", 300, "_invoke"))
    assert not _frame_is_framework(traceback.FrameSummary("", 1, "f"))  # 空路径不误判


def test_format_filtered_traceback_preserves_exception_chain():
    """有异常链（raise ... from）时应保留根因，不丢失 __cause__。"""
    try:
        try:
            raise ValueError("根因：连接被拒")
        except ValueError as ve:
            raise RuntimeError("上层：模型调用失败") from ve
    except RuntimeError:
        rendered = _format_filtered_traceback(sys.exc_info())

    assert "RuntimeError: 上层：模型调用失败" in rendered
    assert "ValueError: 根因：连接被拒" in rendered
    assert "direct cause" in rendered


def test_format_filtered_traceback_filters_flagged_frames():
    """被标记为框架的帧应被过滤；临时把本测试文件加入过滤名单验证。"""
    original = app_logging._FRAME_FILTER_SUBSTRINGS
    app_logging._FRAME_FILTER_SUBSTRINGS = (*original, "test_logging_format")
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            rendered = _format_filtered_traceback(sys.exc_info())
    finally:
        app_logging._FRAME_FILTER_SUBSTRINGS = original

    assert "Traceback" in rendered
    assert "RuntimeError: boom" in rendered
    assert "File " not in rendered  # 测试文件的所有帧均被过滤


def test_console_formatter_includes_context_and_message():
    """控制台 formatter 应输出级别/logger/消息，并注入 request_id 上下文。"""
    formatter = ConsoleFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    token = request_id_ctx.set("req-123")
    try:
        rendered = formatter.format(record)
    finally:
        request_id_ctx.reset(token)

    assert "ERROR" in rendered
    assert "[app.test] hello world" in rendered
    assert "rid=req-123" in rendered


def test_json_formatter_remains_valid_json():
    """文件侧 JsonFormatter 输出仍为合法 JSON，保留结构化字段。"""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=None,
        exc_info=None,
    )
    rendered = formatter.format(record)

    data = json.loads(rendered)
    assert data["message"] == "hello"
    assert data["level"] == "ERROR"
