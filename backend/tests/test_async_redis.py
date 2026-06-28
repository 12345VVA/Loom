"""T3 SSE 订阅异步化测试：async Redis 客户端降级 + subscribe_events 无 Redis 保底心跳。

完整 pubsub 路径需真实 Redis（集成测试范畴），此处验证降级与保底逻辑。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from redis.exceptions import RedisError

from app.core import async_redis as async_redis_module
from app.modules.workflow.service import event_bus


class AsyncRedisClientTestCase(unittest.TestCase):
    def tearDown(self):
        # 复位模块级单例，避免污染其他测试
        async_redis_module._async_client = None
        async_redis_module._async_unavailable = False

    def test_ping_failure_returns_none_and_marks_unavailable(self):
        async def run():
            with (
                patch.object(async_redis_module, "_async_client", None),
                patch.object(async_redis_module, "_async_unavailable", False),
                patch.object(async_redis_module, "AsyncRedis") as mock_redis_cls,
            ):
                mock_instance = AsyncMock()
                mock_instance.ping = AsyncMock(side_effect=RedisError("conn refused"))
                mock_redis_cls.from_url.return_value = mock_instance

                client = await async_redis_module.get_async_redis_client()
                return client, async_redis_module._async_unavailable

        client, unavailable = asyncio.run(run())
        self.assertIsNone(client)
        self.assertTrue(unavailable)

    def test_unavailable_short_circuits_to_none(self):
        async def run():
            with (
                patch.object(async_redis_module, "_async_client", None),
                patch.object(async_redis_module, "_async_unavailable", True),
            ):
                return await async_redis_module.get_async_redis_client()

        self.assertIsNone(asyncio.run(run()))


class SubscribeEventsTestCase(unittest.TestCase):
    def test_no_redis_yields_heartbeat(self):
        """async + sync Redis 均不可用时，订阅生成器降级为心跳（yield None）。"""

        async def fast_sleep(*_args, **_kwargs):
            return None

        async def run():
            gen = event_bus.subscribe_events(1)
            first = await gen.__anext__()
            await gen.aclose()
            return first

        with (
            patch.object(event_bus, "get_async_redis_client", new=AsyncMock(return_value=None)),
            patch.object(event_bus, "get_redis_client", return_value=None),
            patch("asyncio.sleep", fast_sleep),
        ):
            first = asyncio.run(run())
        self.assertIsNone(first)

    def test_subscribe_get_message_exception_yields_heartbeat(self):
        """async pubsub.get_message 抛异常 → 降级心跳，不杀 SSE 流。"""
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(side_effect=ConnectionError("dropped"))
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_client = MagicMock()  # redis.asyncio pubsub() 是同步方法，返回 PubSub 对象
        mock_client.pubsub.return_value = mock_pubsub

        async def fast_sleep(*_a, **_k):
            return None

        async def run():
            gen = event_bus.subscribe_events(1)
            first = await gen.__anext__()
            await gen.aclose()
            return first

        with patch.object(event_bus, "get_async_redis_client", new=AsyncMock(return_value=mock_client)), \
                patch("asyncio.sleep", fast_sleep):
            first = asyncio.run(run())
        self.assertIsNone(first)


if __name__ == "__main__":
    unittest.main()
