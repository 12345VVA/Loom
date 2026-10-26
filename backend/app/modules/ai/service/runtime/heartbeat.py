"""流式心跳保活与流式独立会话（AI-013 拆分，纯搬迁）。"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Iterable

from sqlmodel import Session

# 流式静默心跳间隔：上游超过该时长无任何事件产出时输出 SSE 注释帧保活，
# 避免首 token 等待 / 深度思考期间被中间代理或公网网关（Cloudflare/ALB 默认空闲超时）掐断
_STREAM_HEARTBEAT_INTERVAL_SECONDS = 15.0

# 心跳/结束哨兵：仅在 _with_heartbeat 的内部队列中流转，不会进入业务事件流
_STREAM_HEARTBEAT = object()
_STREAM_DONE = object()


def _with_heartbeat(events: Iterable[dict], interval: float = _STREAM_HEARTBEAT_INTERVAL_SECONDS) -> Iterable[dict]:
    """为同步上游事件流插入心跳哨兵（静默超过 interval 秒时产出 _STREAM_HEARTBEAT）。

    同步生成器阻塞在上游 read 时控制权不回到循环体，无法自行插心跳；
    借一个 pump 线程把"等待下一条事件"转成"带超时的队列等待"。上游异常经
    队列原样透传给主迭代重新 raise，保持现有降级分支语义不变。生成器关闭
    （客户端断开）时通过 stop 事件通知 pump 退出——若其正阻塞在上游 read，
    最迟在下一条数据或 adapter 读超时后退出（daemon 线程兜底）。
    """
    events_queue: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _pump() -> None:
        try:
            for event in events:
                if stop.is_set():
                    break
                events_queue.put(event)
        except BaseException as exc:  # noqa: BLE001 - 需要把上游任意异常转交主迭代处理
            events_queue.put(exc)
        finally:
            events_queue.put(_STREAM_DONE)

    threading.Thread(target=_pump, daemon=True, name="ai-stream-heartbeat-pump").start()
    try:
        while True:
            try:
                item = events_queue.get(timeout=interval)
            except queue.Empty:
                yield _STREAM_HEARTBEAT
                continue
            if item is _STREAM_DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()


async def _with_heartbeat_async(
    events: AsyncIterator[dict], interval: float = _STREAM_HEARTBEAT_INTERVAL_SECONDS
) -> AsyncIterator[dict]:
    """_with_heartbeat 的异步形态（异步审查 P0-4）：静默超过 interval 秒产出
    _STREAM_HEARTBEAT，等待全程零线程占用。

    ⚠️ 不得用 ``asyncio.wait_for(anext(aiter))`` 实现超时——超时会 cancel 对源
    生成器的读取推进，源被中断后再 anext 直接 StopAsyncIteration，表现为流静默
    截断。这里用非取消式 ``asyncio.wait``：超时仅产心跳，读取任务保持挂起、
    下轮复用同一任务；退出时才取消。"""
    aiter = events.__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(aiter))
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield _STREAM_HEARTBEAT
                continue
            try:
                yield pending.result()
            except StopAsyncIteration:
                return
            pending = None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()


def _independent_session(request_session: Session) -> Session:
    """为流式生成器创建与请求会话同库的独立 Session。

    流式生成器由 Starlette 在 AnyIO 线程池中迭代,线程与创建请求会话的事件循环不同,
    而 SQLAlchemy Session 非线程安全(流式专项审查 P1)。这里按请求会话的 bind 另开
    会话:生产环境与请求同库,测试环境天然指向用例自身的内存库引擎(make_test_engine)。
    不能改用全局 SessionLocal——其绑定全局 engine,会写穿测试隔离。
    """
    return Session(request_session.get_bind())
