"""请求体预读合并中间件（纯 ASGI）。

背景：全局中间件栈大量使用 starlette BaseHTTPMiddleware，其响应期断连监听
链（StreamingResponse.listen_for_disconnect → 各层 wrapped_receive）在请求
体消费完毕后只接受 http.disconnect 一条消息；一旦服务器消息队列里出现残余
的 http.request 分片（代理重传 / TLS 分段错位下，下游已收到 more_body=False
判定读全之后仍可能到达），监听链会把它当意外消息拉出，触发
`RuntimeError: Unexpected message received: http.request`，响应协程崩溃、
流式响应首帧后即断（agent 对话走查实测）。

本中间件置于所有 BaseHTTPMiddleware 之外，在进入业务链前把请求体一次读全、
合并为单条消息，并丢弃「声明完整之后」才到达的残余分片——下游监听链从此
只会等到 disconnect。异常路径（断连 / 超限）不合并、按原样回放，保真上游
语义。
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 预读缓冲上限：仅覆盖常规 JSON/表单体（OperationLog 的 1MB 记录上限另计），
# 超限即放弃合并、原样透传，保真大文件上传
DEFAULT_MAX_BYTES = 4 * 1024 * 1024

# 只有可能携带请求体的方法需要合并；GET/HEAD/OPTIONS 单条消息投递本就无残留，
# 直接透传
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BodyBufferMiddleware:
    """合并请求体分片，杜绝 BaseHTTPMiddleware 监听链拉到残留 http.request。"""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        raw: list[Message] = []
        total = 0
        overflow = False
        clean_end = False

        while True:
            message = await receive()
            raw.append(message)
            msg_type = message.get("type")
            if msg_type == "http.disconnect":
                break
            if msg_type != "http.request":
                # 未知消息类型：保守起见停止缓冲，按原样回放
                break
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                overflow = True
                break
            if not message.get("more_body", False):
                clean_end = True
                break

        # 仅「干净读全」才合并为单条；断连/超限/未知消息原样回放 + 后续透传
        merged = clean_end and not overflow
        if merged:
            replay: list[Message] = [
                {
                    "type": "http.request",
                    "body": b"".join(m.get("body", b"") for m in raw),
                    "more_body": False,
                }
            ]
        else:
            replay = list(raw)

        async def buffered_receive() -> Message:
            if replay:
                return replay.pop(0)
            while True:
                message = await receive()
                if merged and message.get("type") == "http.request":
                    # 合并态下 body 已声明完整，此后到达的残余分片（代理重传 /
                    # 分段错位投递）一律丢弃——这正是击穿 SSE 监听链的根因消息
                    continue
                return message

        await self.app(scope, buffered_receive, send)
