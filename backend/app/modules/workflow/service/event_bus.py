"""
跨进程工作流事件总线（Redis pub/sub 桥接）。
"""

import asyncio
import json
import logging
from typing import Any

from app.core.async_redis import get_async_redis_client
from app.modules.base.service.cache_service import get_redis_client

logger = logging.getLogger(__name__)

WORKFLOW_EVENT_CHANNEL_PREFIX = "workflow:events:"


def publish_event(instance_id: int, event_type: str, data: Any):
    """
    发布工作流事件。双写 Redis pub/sub（跨进程）和进程内 listener（降级兼容）。
    Celery Worker 中调用时通过 Redis 送达 Web 进程；Web 进程内直接调用时走 listener。
    """
    payload = json.dumps(
        {"instance_id": instance_id, "event_type": event_type, "data": data},
        ensure_ascii=False,
        default=str,
    )

    # 1. Redis pub/sub — 跨进程桥接
    client = get_redis_client()
    if client is not None:
        try:
            channel = f"{WORKFLOW_EVENT_CHANNEL_PREFIX}{instance_id}"
            client.publish(channel, payload)
        except Exception:
            logger.debug("Redis publish failed for instance %d", instance_id, exc_info=True)

    # 2. 进程内 listener（workflow_event_listeners）已移除：该列表无注册点（死代码），
    # 且发布者通常在 Celery Worker 进程、订阅者在 Web 进程，进程内回调对跨进程事件无效。
    # 跨进程事件统一经 Redis pub/sub 由 subscribe_events 订阅。


async def subscribe_events(instance_id: int):
    """
    异步生成器，从 Redis pub/sub 订阅实例事件，yield 给 SSE 端点。
    定期返回 None 作为心跳，保持长连接存活。

    优先使用 redis.asyncio 原生异步 pubsub（不占用 anyio 线程池）；异步客户端不可用时
    降级为同步 pubsub + asyncio.to_thread（每连接独占线程池 worker，仅作保底）。
    """
    channel = f"{WORKFLOW_EVENT_CHANNEL_PREFIX}{instance_id}"

    async_client = await get_async_redis_client()
    if async_client is not None:
        pubsub = async_client.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                try:
                    message = await pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True)
                except Exception as exc:
                    logger.warning("订阅实例 %d 事件断开，降级心跳等待前端重连: %s", instance_id, exc)
                    yield None
                    await asyncio.sleep(1)
                    continue
                if message and message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except json.JSONDecodeError:
                        pass
                else:
                    yield None  # heartbeat
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        return

    # 降级：无 async Redis，回退同步阻塞 pubsub + to_thread（保底，占用线程池）
    sync_client = get_redis_client()
    if sync_client is None:
        while True:
            await asyncio.sleep(5)
            yield None
        return

    pubsub = sync_client.pubsub()
    pubsub.subscribe(channel)
    try:
        while True:
            try:
                message = await asyncio.to_thread(lambda: pubsub.get_message(timeout=1.0))
            except Exception as exc:
                logger.warning("订阅实例 %d 事件断开（降级路径），心跳: %s", instance_id, exc)
                yield None
                await asyncio.sleep(1)
                continue
            if message and message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except json.JSONDecodeError:
                    pass
            else:
                yield None  # heartbeat
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
