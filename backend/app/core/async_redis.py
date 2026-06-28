"""异步 Redis 客户端（供 SSE 订阅等真异步 I/O 场景使用）。

与 cache_service 的同步 Redis 客户端使用**独立连接池**，避免同步/异步客户端混用
导致连接管理冲突。懒初始化：首次获取时建立连接池，Web 进程内单例。
Redis 不可用时返回 None，调用方（如 subscribe_events）负责降级。
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_async_client: AsyncRedis | None = None
_async_unavailable = False


async def get_async_redis_client() -> AsyncRedis | None:
    """获取异步 Redis 客户端单例，不可用时返回 None。"""
    global _async_client, _async_unavailable

    if _async_unavailable:
        return None

    if _async_client is None:
        try:
            _async_client = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
            await _async_client.ping()
        except (RedisError, OSError) as exc:
            logger.warning("异步 Redis 不可用，SSE 订阅将降级为同步轮询: %s", exc)
            _async_unavailable = True
            _async_client = None
            return None

    return _async_client


async def close_async_redis_client() -> None:
    """关闭异步 Redis 连接池（应用 shutdown 时调用）。"""
    global _async_client, _async_unavailable
    if _async_client is not None:
        try:
            await _async_client.aclose()
        except Exception as exc:
            logger.debug("关闭异步 Redis 连接池失败: %s", exc)
        _async_client = None
        _async_unavailable = False
