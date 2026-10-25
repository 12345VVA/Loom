"""ASGI 全链路异常兜底与进程级异常钩子回归。

覆盖：中间件/流式响应协程异常的规范化记录与统一 500 回退、SSE 半途崩溃不冒出、
异常组解包、致命异常放行、进程钩子（子线程/事件循环）、uvicorn logger 收编。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
import threading
import unittest

from app.core.logging import configure_logging
from app.framework.middleware.exception_guard import (
    ExceptionGuardMiddleware,
    install_process_exception_hooks,
)


def _http_scope(method: str = "POST", path: str = "/x") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }


async def _receive() -> dict:
    return {"type": "http.disconnect"}


async def _drive(app, scope: dict | None = None, send=None) -> list[dict]:
    sent: list[dict] = []

    async def default_send(message: dict) -> None:
        sent.append(message)

    await app(scope or _http_scope(), _receive, send or default_send)
    return sent


def _response_payload(sent: list[dict]) -> dict:
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return json.loads(body.decode("utf-8"))


class ExceptionGuardMiddlewareTests(unittest.TestCase):
    def test_normal_request_passthrough(self) -> None:
        async def ok_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        sent = asyncio.run(_drive(ExceptionGuardMiddleware(ok_app)))
        self.assertEqual(sent[0]["status"], 200)

    def test_middleware_crash_returns_unified_500(self) -> None:
        """响应未开始时崩溃：统一 500 envelope + 规范化日志含根因。"""

        async def boom_app(scope, receive, send):
            raise RuntimeError("中间件链路爆炸")

        with self.assertLogs("app.exceptions", level="ERROR") as captured:
            sent = asyncio.run(_drive(ExceptionGuardMiddleware(boom_app)))

        self.assertEqual(sent[0]["type"], "http.response.start")
        self.assertEqual(sent[0]["status"], 500)
        payload = _response_payload(sent)
        self.assertEqual(payload["message"], "服务器内部错误")
        # 回退响应头携带 request_id，客户端报障可与日志对账
        headers = dict(sent[0].get("headers") or [])
        self.assertIn(b"x-request-id", headers)
        self.assertIn("RuntimeError: 中间件链路爆炸", "\n".join(captured.output))

    def test_sse_mid_stream_crash_logged_not_raised(self) -> None:
        """SSE 半途崩溃：异常被吞（不冒到 uvicorn 打脏堆栈），已发首帧保留。"""

        async def sse_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"data: 1\n\n", "more_body": True})
            raise RuntimeError("流式响应中途崩溃")

        with self.assertLogs("app.exceptions", level="ERROR") as captured:
            sent = asyncio.run(_drive(ExceptionGuardMiddleware(sse_app)))

        self.assertEqual(sent[0]["type"], "http.response.start")
        self.assertTrue(any("流式响应中途崩溃" in line for line in captured.output))

    def test_exception_group_unwrapped_to_root_cause(self) -> None:
        """anyio TaskGroup 异常组：解包记录根因子异常。"""

        async def group_app(scope, receive, send):
            try:
                raise RuntimeError("组内根因")
            except RuntimeError:
                raise ExceptionGroup("unhandled errors in a TaskGroup", [RuntimeError("组内根因")])

        with self.assertLogs("app.exceptions", level="ERROR") as captured:
            sent = asyncio.run(_drive(ExceptionGuardMiddleware(group_app)))

        self.assertEqual(sent[0]["status"], 500)
        self.assertIn("组内根因", "\n".join(captured.output))

    def test_fatal_exception_in_group_reraised(self) -> None:
        """异常组含 KeyboardInterrupt 时放行（原样重抛），不吞致命异常。"""

        async def fatal_app(scope, receive, send):
            raise BaseExceptionGroup("mixed", [KeyboardInterrupt()])

        with self.assertRaises(BaseExceptionGroup) as ctx:
            asyncio.run(_drive(ExceptionGuardMiddleware(fatal_app)))
        self.assertIsInstance(ctx.exception.exceptions[0], KeyboardInterrupt)

    def test_fallback_send_failure_swallowed(self) -> None:
        """回退响应时客户端已断开：send 失败不向 uvicorn 再抛异常。"""

        async def boom_app(scope, receive, send):
            raise RuntimeError("双炸")

        async def broken_send(message: dict) -> None:
            raise ConnectionError("客户端断开")

        with self.assertLogs("app.exceptions", level="ERROR"):
            asyncio.run(_drive(ExceptionGuardMiddleware(boom_app), send=broken_send))


class ProcessHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_sys_hook = sys.excepthook
        self._saved_thread_hook = threading.excepthook

    def tearDown(self) -> None:
        sys.excepthook = self._saved_sys_hook
        threading.excepthook = self._saved_thread_hook

    def test_thread_hook_logs_uncaught(self) -> None:
        """子线程未捕获异常应被规范化记录。"""
        install_process_exception_hooks()
        args = threading.ExceptHookArgs((RuntimeError, RuntimeError("线程内爆炸"), None, threading.current_thread()))
        with self.assertLogs("app.exceptions", level="CRITICAL") as captured:
            threading.excepthook(args)
        self.assertIn("线程内爆炸", "\n".join(captured.output))

    def test_loop_handler_logs_orphan_task_exception(self) -> None:
        """事件循环处理器应记录孤儿任务异常（Task exception was never retrieved 场景）。"""

        async def scenario() -> None:
            install_process_exception_hooks()  # 事件循环内调用，loop 钩子生效
            loop = asyncio.get_running_loop()
            with self.assertLogs("app.exceptions", level="ERROR") as captured:
                loop.call_exception_handler(
                    {"exception": RuntimeError("孤儿任务异常"), "message": "Task exception was never retrieved"}
                )
                await asyncio.sleep(0.01)
            self.assertIn("孤儿任务异常", "\n".join(captured.output))

        asyncio.run(scenario())


class UvicornLoggerAdoptionTests(unittest.TestCase):
    def test_configure_logging_adopts_uvicorn_loggers(self) -> None:
        """configure_logging 应收编 uvicorn 系 logger（清 handler、改道 root formatter）。"""
        root = logging.getLogger()
        saved_handlers = root.handlers[:]
        saved_level = root.level
        uv_loggers = [logging.getLogger(n) for n in ("uvicorn", "uvicorn.error", "uvicorn.access")]
        saved = [(lg.handlers[:], lg.propagate, lg.level) for lg in uv_loggers]
        with tempfile.TemporaryDirectory() as log_dir:
            try:
                configure_logging(log_dir=log_dir)
                for lg in uv_loggers:
                    self.assertEqual(lg.handlers, [])
                    self.assertTrue(lg.propagate)
            finally:
                root.handlers[:] = saved_handlers
                root.setLevel(saved_level)
                for lg, (handlers, propagate, level) in zip(uv_loggers, saved):
                    lg.handlers[:] = handlers
                    lg.propagate = propagate
                    lg.setLevel(level)


if __name__ == "__main__":
    unittest.main()
