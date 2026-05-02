"""
进程内轻量事件总线。
"""
from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from app.modules.base.service.cache_service import get_redis_client

logger = logging.getLogger(__name__)
EventHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]

_subscribers: dict[str, list[EventHandler]] = defaultdict(list)
_backend: EventBackend | None = None


class EventBackend:
    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class RedisStreamEventBackend(EventBackend):
    def __init__(self, stream_prefix: str = "loom:events"):
        self.stream_prefix = stream_prefix

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        client = get_redis_client()
        if client is None:
            logger.warning("Redis 不可用，跨进程事件未投递: %s", event_name)
            return
        client.xadd(f"{self.stream_prefix}:{event_name}", {"payload": repr(payload)})


def set_event_backend(backend: EventBackend | None) -> None:
    global _backend
    _backend = backend


def subscribe(event_name: str, handler: EventHandler) -> None:
    if handler not in _subscribers[event_name]:
        _subscribers[event_name].append(handler)


def unsubscribe(event_name: str, handler: EventHandler) -> None:
    if handler in _subscribers[event_name]:
        _subscribers[event_name].remove(handler)


async def publish(event_name: str, payload: dict[str, Any] | None = None) -> None:
    event_payload = payload or {}
    if _backend is not None:
        await _backend.publish(event_name, event_payload)
    for handler in list(_subscribers.get(event_name, [])):
        try:
            result = handler(event_payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("事件处理失败: %s", event_name)
