"""工作流异常 → 可读错误消息的统一转换。

此前执行监控的 error_message 只有 ValueError 透出原文，其余一律替换为
"执行失败，发生内部错误。"，失败节点与原因全部丢失。本模块把链路上各层
异常（节点包装 NodeExecutionError、AI 厂商 UpstreamApiError、接口层
HTTPException、程序性异常）折叠成单行可落库/可展示的中文消息，
供实例终态、SSE failed 事件、失败通知与单节点测试共用。
"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException

from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.workflow.service.compiler import NodeExecutionError

_FALLBACK = "执行失败，发生内部错误。"
# cause 最多展开一层（NodeExecutionError → cause），防止异常链过长串出底层网络栈/URL
_MAX_UNWRAP_DEPTH = 2
_WS_RE = re.compile(r"\s+")


def friendly_error_message(
    e: BaseException,
    node_names: dict[str, str] | None = None,
    *,
    max_len: int = 500,
) -> str:
    """把异常折叠为单行可读消息：定位节点 + 原因。

    node_names：node_id → 展示名映射（有则把 NodeExecutionError 的技术 id 换成节点名）。
    max_len：截断长度，实例 error_message 列宽 1000，默认 500 留余量。
    """
    names = node_names or {}
    if isinstance(e, NodeExecutionError):
        display = names.get(e.node_id) or e.node_id
        cause = _unwrap(e.cause, 1, names) if e.cause is not None else "未知原因"
        msg = f"节点「{display}」执行失败（已尝试 {e.attempts} 次）: {cause}"
    else:
        msg = _unwrap(e, 0, names)
    msg = _clean(msg)[:max_len]
    return msg or _FALLBACK


def _unwrap(exc: BaseException | None, depth: int, names: dict[str, str] | None = None) -> str:
    """单层异常 → 文本。按异常类型取可读部分，不沿 __cause__ 链递归。"""
    if exc is None:
        return ""
    if isinstance(exc, NodeExecutionError):
        mapping = names or {}
        if depth >= _MAX_UNWRAP_DEPTH:
            return mapping.get(exc.node_id) or exc.node_id
        display = mapping.get(exc.node_id) or exc.node_id
        cause = _unwrap(exc.cause, depth + 1, mapping) if exc.cause is not None else "未知原因"
        return f"节点「{display}」执行失败（已尝试 {exc.attempts} 次）: {cause}"
    if isinstance(exc, HTTPException):
        # str(HTTPException) 是 "400: detail"，取 detail 去掉冗余状态码前缀；
        # detail 允许 dict/list（FastAPI），repr 形式难读，序列化为 JSON
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        if isinstance(detail, (dict, list)):
            return json.dumps(detail, ensure_ascii=False)
        return str(detail)
    if isinstance(exc, UpstreamApiError):
        msg = str(exc)
        if getattr(exc, "request_id", None):
            msg = f"{msg}（请求ID: {exc.request_id}）"
        return msg
    text = str(exc)
    if not text:
        # 部分网络异常 str 为空，退回类型名至少给出方向
        return type(exc).__name__
    if isinstance(exc, ValueError):
        return text
    # 程序性异常带类型名前缀（KeyError('x') 的 str 只有 "'x'"，无类型名难定位）
    return f"{type(exc).__name__}: {text}"


def _clean(msg: str) -> str:
    """换行/制表压缩为单行空格，去首尾空白——error_message 是单行展示字段。"""
    return _WS_RE.sub(" ", msg).strip()
