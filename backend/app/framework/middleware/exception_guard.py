"""ASGI 全链路异常兜底与进程级异常钩子。

背景：FastAPI 的 Exception handler 只覆盖路由函数内异常；中间件链与流式响应
协程（SSE 长挂起）中抛出的异常会一路冒到 uvicorn，由 uvicorn 以原始堆栈打印
（ExceptionGroup 全展开、无 request_id 上下文、不走应用日志配置的框架帧过滤），
且客户端拿到的是无响应头的连接中断。

ExceptionGuardMiddleware 置于 CORS 之内、全部业务中间件之外：
- 捕获一切冒出的异常（含 anyio TaskGroup 的 ExceptionGroup），解包根因后经应用
  logger 规范化记录（框架帧过滤 + 异常组展开 + request_id 上下文）；
- 响应未开始时回退统一 500 JSON（error envelope，再经 CORS 层补 CORS 头）；
- 响应已开始（SSE 半途崩溃）时只记录日志并吞掉异常，避免 uvicorn 重复打印脏堆栈。

install_process_exception_hooks 补齐进程级兜底：主线程/子线程未捕获异常与
asyncio 孤儿任务异常（"Task exception was never retrieved"）统一走应用日志，
由 ConsoleFormatter 完成堆栈规范化。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx, unpack_exception

logger = logging.getLogger("app.exceptions")


def _group_has_fatal(group: BaseExceptionGroup) -> bool:
    """异常组叶子中是否含 KeyboardInterrupt/SystemExit——此类不可吞，须放行。"""
    for sub in group.exceptions:
        if isinstance(sub, BaseExceptionGroup):
            if _group_has_fatal(sub):
                return True
        elif isinstance(sub, (KeyboardInterrupt, SystemExit)):
            return True
    return False


class ExceptionGuardMiddleware:
    """捕获全部 ASGI 链路异常：规范化记录 + 未开始响应时回退统一 500。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            try:
                await self.app(scope, receive, send)
            except Exception as exc:
                self._log(scope, exc, uuid4().hex)
            return

        response_started = False
        # 兜底场景内侧 RequestIdMiddleware 的 contextvar 已随其 finally reset，
        # 取原始 x-request-id 头或现生成；日志与回退响应头共用，保证可关联
        request_id = request_id_ctx.get() or uuid4().hex

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseExceptionGroup as group:
            if _group_has_fatal(group):
                raise
            self._log(scope, group, request_id)
            await self._fallback(send, response_started, request_id)
        except Exception as exc:
            self._log(scope, exc, request_id)
            await self._fallback(send, response_started, request_id)

    def _log(self, scope: Scope, exc: BaseException, request_id: str) -> None:
        root = unpack_exception(exc)
        token = request_id_ctx.set(request_id)
        try:
            logger.error(
                "ASGI 链路未捕获异常: %s: %s",
                type(root).__name__,
                root,
                extra={
                    "error_type": type(root).__name__,
                    "error_message": str(root),
                    "path": scope.get("path"),
                    "method": scope.get("method"),
                },
                exc_info=exc,
            )
        finally:
            request_id_ctx.reset(token)

    async def _fallback(self, send: Send, response_started: bool, request_id: str) -> None:
        if response_started:
            return
        from app.framework.api.error_codes import status_to_error_code

        body = json.dumps(
            {
                "code": status_to_error_code(500),
                "message": "服务器内部错误",
                "data": None,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"x-request-id", request_id.encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
        except Exception:
            # 客户端已断开等场景下响应回退失败：异常已在上方记录，静默收尾
            pass


def install_process_exception_hooks() -> None:
    """进程级兜底钩子：在 FastAPI lifespan 启动时调用（需事件循环已运行）。"""
    if sys.excepthook is sys.__excepthook__:
        # 未被其他库（调试器等）接管时才接管，避免破坏既有行为
        def _sys_hook(tp, value, tb) -> None:
            logger.critical("主线程未捕获异常: %s: %s", tp.__name__, value, exc_info=(tp, value, tb))
            sys.__excepthook__(tp, value, tb)

        sys.excepthook = _sys_hook

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "子线程 %s 未捕获异常: %s: %s",
            getattr(args.thread, "name", "?"),
            args.exc_type.__name__,
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _loop_handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        # 覆盖孤儿任务异常（"Task exception was never retrieved"）与回调异常
        exc = context.get("exception")
        message = context.get("message", "事件循环异常")
        if exc is not None:
            logger.error("asyncio 事件循环: %s", message, exc_info=exc)
        else:
            logger.error("asyncio 事件循环: %s (%s)", message, context or {})

    loop.set_exception_handler(_loop_handler)
