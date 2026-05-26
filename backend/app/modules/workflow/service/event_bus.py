"""
跨进程工作流事件总线（Redis pub/sub 桥接）。
"""
import asyncio
import json
import logging
from typing import Any

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

    # 2. 进程内 listener — 兼容无 Redis 的开发环境
    from app.modules.workflow.service.workflow_service import workflow_event_listeners

    for listener in workflow_event_listeners:
        try:
            listener(instance_id, event_type, data)
        except Exception:
            pass


async def subscribe_events(instance_id: int):
    """
    异步生成器，从 Redis pub/sub 订阅实例事件，yield 给 SSE 端点。
    定期返回 None 作为心跳，保持长连接存活。
    """
    client = get_redis_client()
    if client is None:
        while True:
            await asyncio.sleep(5)
            yield None
        return

    channel = f"{WORKFLOW_EVENT_CHANNEL_PREFIX}{instance_id}"
    pubsub = client.pubsub()
    pubsub.subscribe(channel)

    try:
        while True:
            message = await asyncio.to_thread(lambda: pubsub.get_message(timeout=1.0))
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
