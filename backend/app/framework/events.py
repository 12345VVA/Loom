"""
进程内轻量事件总线。
"""
from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)
EventHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]

_subscribers: dict[str, list[EventHandler]] = defaultdict(list)


def subscribe(event_name: str, handler: EventHandler) -> None:
    if handler not in _subscribers[event_name]:
        _subscribers[event_name].append(handler)


def unsubscribe(event_name: str, handler: EventHandler) -> None:
    if handler in _subscribers[event_name]:
        _subscribers[event_name].remove(handler)


async def publish(event_name: str, payload: dict[str, Any] | None = None) -> None:
    event_payload = payload or {}
    for handler in list(_subscribers.get(event_name, [])):
        try:
            result = handler(event_payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("事件处理失败: %s", event_name)
