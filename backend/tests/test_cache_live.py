"""真 Redis 下的缓存语义验证（复审 N6）。

降级路径（进程内 get+delete）在单元测试中已被覆盖；本文件验证 **真 Redis** 下的
原子性契约——GETDEL 并发消费恰一次。无可用 Redis 时整体 skip（D6 先例：
缺基础设施自动停用，配置后即启用）。
"""

from __future__ import annotations

import threading
import unittest

from app.modules.base.service.cache_service import get_redis_client


class RedisGetdelAtomicityTests(unittest.TestCase):
    """GETDEL 并发原子性：N 个线程并发消费同一 key，恰有一个拿到值（验证码防重放的根基）。"""

    def setUp(self):
        self.client = get_redis_client()
        if self.client is None:
            self.skipTest("无可用 Redis（真 Redis 原子性验证跳过——D6 先例）")

    def tearDown(self):
        if self.client is not None:
            try:
                self.client.delete("verify:slider:live-getdel-test")
            except Exception:
                pass

    def test_getdel_exactly_once_under_concurrency(self):
        key = "verify:slider:live-getdel-test"
        self.client.set(key, "1", ex=60)

        results: list = []
        lock = threading.Lock()

        def worker():
            try:
                value = self.client.getdel(key)
                with lock:
                    results.append(value)
            except Exception as exc:  # 连接异常也要计数，防止静默吞掉导致误判
                with lock:
                    results.append(f"__error__:{exc}")

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        errors = [r for r in results if isinstance(r, str) and r.startswith("__error__")]
        self.assertEqual(errors, [], f"并发 GETDEL 出现异常: {errors}")
        got = [r for r in results if r == "1"]
        self.assertEqual(
            len(got),
            1,
            f"16 线程并发 GETDEL 必须恰一次成功，实际 {len(got)} 次（防重放契约破坏）",
        )

    def test_getdel_second_read_misses(self):
        """顺序语义：消费一次后再次读取为空（一次性消费）。"""
        key = "verify:slider:live-getdel-test"
        self.client.set(key, "1", ex=60)
        self.assertEqual(self.client.getdel(key), "1")
        self.assertIsNone(self.client.getdel(key))


if __name__ == "__main__":
    unittest.main()
