"""BodyBufferMiddleware 回归：请求体残余分片不得击穿 SSE 长挂起响应。

根因（agent 对话走查实测）：starlette BaseHTTPMiddleware 的响应期断连监听链
（listen_for_disconnect → 各层 wrapped_receive）在请求体消费完毕后只接受
http.disconnect；服务器队列里若出现「下游判定读全之后」仍到达的残余
http.request 分片（代理重传 / 分段错位），监听链把它当意外消息拉出，触发
`RuntimeError: Unexpected message received: http.request`，响应协程崩溃、
流式响应首帧后即断。
"""

import asyncio
import unittest

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from app.framework.middleware.body_buffer import BodyBufferMiddleware


def _http_scope(method: str = "POST") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }


class _ScriptedReceive:
    """按脚本队列投递消息。

    ``deferred`` 里的消息在主队列耗尽后才逐条投递——模拟「下游判定 body
    读全之后」才到达的错位残余分片（代理重传 / TLS 分段）；deferred 也耗尽
    后挂起（连接保持），disconnect 置位后投递。
    """

    def __init__(self, messages: list[dict], deferred: list[dict] | None = None):
        self.queue: list[dict] = list(messages)
        self.deferred: list[dict] = list(deferred or [])
        self._closed = asyncio.Event()

    def disconnect(self) -> None:
        self._closed.set()

    async def __call__(self) -> dict:
        if self.queue:
            return self.queue.pop(0)
        if self.deferred:
            return self.deferred.pop(0)
        await self._closed.wait()
        return {"type": "http.disconnect"}


def _chunk(body: bytes, more: bool) -> dict:
    return {"type": "http.request", "body": body, "more_body": more}


# 预投分片两段（正常读全）+ 错位残余（读全之后才到达）
_FRAGMENTED_BODY = [_chunk(b'{"q": "he', True), _chunk(b'llo"}', False)]
_RESIDUE = [_chunk(b'llo"}', False)]


async def _sse_endpoint_app(scope, receive, send) -> None:
    """模拟路由：读全 body 后返回 SSE 长响应。"""
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body", False):
            break

    async def gen():
        yield b"data: first\n\n"
        await asyncio.sleep(0.02)
        yield b"data: second\n\n"

    await StreamingResponse(gen(), media_type="text/event-stream")(scope, receive, send)


def _passthrough_basehttp(app):
    """裸 BaseHTTPMiddleware 包装（透传，但仍在 receive 链上引入 wrapped_receive）。"""

    class Passthrough(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await call_next(request)

    return Passthrough(app)


async def _drive(app, receive) -> list[dict]:
    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    await app(_http_scope(), receive, send)
    return sent


def _response_body(sent: list[dict]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


class BodyBufferSseTests(unittest.TestCase):
    def test_bare_basehttp_stack_breaks_on_residue(self) -> None:
        """反向基线：裸 BaseHTTPMiddleware 栈遇错位残余分片 + SSE 挂起即崩（bug 存在性）。

        复现产物即线上报错原文：RuntimeError: Unexpected message received: http.request
        （collapse_excgroups 会把单成员 ExceptionGroup 解包为裸 RuntimeError）。
        """
        app = _passthrough_basehttp(_sse_endpoint_app)
        recv = _ScriptedReceive(_FRAGMENTED_BODY, deferred=_RESIDUE)
        with self.assertRaises(RuntimeError, msg="Unexpected message received: http.request"):
            asyncio.run(_drive(app, recv))

    def test_body_buffer_keeps_sse_alive_with_residue(self) -> None:
        """修复正向：Buffer 包裹后同一场景完整收流（残余分片被吞）。"""
        app = BodyBufferMiddleware(_passthrough_basehttp(_sse_endpoint_app))
        recv = _ScriptedReceive(_FRAGMENTED_BODY, deferred=_RESIDUE)
        sent = asyncio.run(_drive(app, recv))
        recv.disconnect()
        body = _response_body(sent)
        self.assertIn(b"data: first", body)

        self.assertIn(b"data: second", body)


class BodyBufferBehaviorTests(unittest.TestCase):
    def _capture(self, count: int):
        seen: list[dict] = []

        async def downstream(scope, receive, send) -> None:
            for _ in range(count):
                seen.append(await receive())

        return downstream, seen

    def test_merges_clean_fragmented_body_into_single_message(self) -> None:
        downstream, seen = self._capture(1)
        asyncio.run(
            _drive(BodyBufferMiddleware(downstream), _ScriptedReceive([_chunk(b"a", True), _chunk(b"bc", False)]))
        )
        self.assertEqual(seen, [{"type": "http.request", "body": b"abc", "more_body": False}])

    def test_single_chunk_body_still_merged_idempotently(self) -> None:
        downstream, seen = self._capture(1)
        asyncio.run(_drive(BodyBufferMiddleware(downstream), _ScriptedReceive([_chunk(b'{"q": 1}', False)])))
        self.assertEqual(seen, [{"type": "http.request", "body": b'{"q": 1}', "more_body": False}])

    def test_residue_after_clean_end_is_swallowed(self) -> None:
        """合并态下读全之后的残余 http.request 被丢弃，下游只等到 disconnect。"""
        downstream, seen = self._capture(2)
        recv = _ScriptedReceive([_chunk(b"a", False)], deferred=[_chunk(b"a", False)])

        async def scenario() -> None:
            task = asyncio.create_task(_drive(BodyBufferMiddleware(downstream), recv))
            await asyncio.sleep(0.05)
            recv.disconnect()
            await task

        asyncio.run(scenario())
        self.assertEqual(
            seen,
            [
                {"type": "http.request", "body": b"a", "more_body": False},
                {"type": "http.disconnect"},
            ],
        )

    def test_overflow_replays_raw_chunks_then_passthrough(self) -> None:
        downstream, seen = self._capture(2)
        asyncio.run(
            _drive(
                BodyBufferMiddleware(downstream, max_bytes=1),
                _ScriptedReceive([_chunk(b"abc", True), _chunk(b"def", False)]),
            )
        )
        self.assertEqual([m["body"] for m in seen], [b"abc", b"def"])
        self.assertTrue(seen[0]["more_body"])

    def test_disconnect_mid_body_replayed_as_is(self) -> None:
        recv = _ScriptedReceive([_chunk(b"abc", True), {"type": "http.disconnect"}])
        downstream, seen = self._capture(2)
        asyncio.run(_drive(BodyBufferMiddleware(downstream), recv))
        self.assertEqual(seen[0]["type"], "http.request")
        self.assertTrue(seen[0]["more_body"])
        self.assertEqual(seen[1]["type"], "http.disconnect")

    def test_get_request_passthrough_without_buffering(self) -> None:
        recv = _ScriptedReceive([_chunk(b"", False)])
        downstream, seen = self._capture(1)

        async def run() -> None:
            await downstream(_http_scope(method="GET"), recv, None)

        asyncio.run(run())
        # 未缓冲：下游拿到的就是原始 receive 投递的消息
        self.assertEqual(seen, [{"type": "http.request", "body": b"", "more_body": False}])


if __name__ == "__main__":
    unittest.main()
