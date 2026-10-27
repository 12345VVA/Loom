"""运行时指标回归（异步审查·可观测性）。

覆盖：路径归一化（路由模板/404 截断）/ 序列上限（P2-8 防泄漏）/ gauge 渲染 /
SSE 连接计数配对 / 队列积压采集口径（Σ优先级键 + unacked 单列）。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.core.config import settings
from app.framework.middleware import metrics as metrics_module
from app.framework.middleware.metrics import (
    MetricsMiddleware,
    _normalize_path,
    render_metrics,
    set_gauge,
    sse_connection_closed,
    sse_connection_opened,
)


def _kombu_suffix_count() -> int:
    from main import _KOMBU_PRI_SUFFIXES

    return len(_KOMBU_PRI_SUFFIXES)


class MetricsPathNormalizationTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(settings, "METRICS_ENABLED", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        metrics_module._requests.clear()
        self.addCleanup(metrics_module._requests.clear)

    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/uploads/{file_path:path}")
        def upload(file_path: str):  # noqa: ANN202 - 测试路由
            return {"ok": True}

        return app

    def test_matched_route_uses_template_path(self):
        """P2-8：匹配路由记模板——/uploads/<date>/<uuid> 收敛为单条序列。"""
        app = self._build_app()
        with TestClient(app) as client:
            client.get("/uploads/20261027/abc.png")
        self.assertIn(("GET", "/uploads/{file_path:path}", 200), metrics_module._requests)
        self.assertNotIn(("GET", "/uploads/20261027/abc.png", 200), metrics_module._requests)

    def test_unmatched_path_truncated(self):
        """未匹配（404 探测等）回退原 path 并截断 120 字符，兜住长尾。"""
        app = self._build_app()
        with TestClient(app) as client:
            client.get("/" + "x" * 300)
        overlong = [key for key in metrics_module._requests if len(key[1]) > 120]
        self.assertEqual(overlong, [])

    def test_normalize_path_direct(self):
        route = SimpleNamespace(path="/items/{item_id}")
        self.assertEqual(_normalize_path({"route": route, "path": "/items/42"}), "/items/{item_id}")
        self.assertEqual(_normalize_path({"path": "/" + "y" * 300}), "/" + "y" * 119)


class MetricsSeriesCapTestCase(unittest.TestCase):
    def test_counter_overflow_dropped_and_counted(self):
        """P2-8：序列达上限后新序列并入 overflow 聚合计数器丢弃，不无界增长。"""
        series: dict = {}
        for index in range(metrics_module._MAX_SERIES_PER_DICT):
            metrics_module._bump_counter(series, ("GET", f"p{index}", 200))
        self.assertEqual(len(series), metrics_module._MAX_SERIES_PER_DICT)
        before = metrics_module._series_overflow_total
        metrics_module._bump_counter(series, ("GET", "p-new", 200))
        self.assertEqual(len(series), metrics_module._MAX_SERIES_PER_DICT)
        self.assertEqual(metrics_module._series_overflow_total, before + 1)

    def test_existing_series_keeps_incrementing_at_cap(self):
        series: dict = {"existing": 1}
        with patch.object(metrics_module, "_MAX_SERIES_PER_DICT", 1):
            metrics_module._bump_counter(series, "existing")
        self.assertEqual(series["existing"], 2)


class GaugeRenderTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(metrics_module._gauges.clear)

    def test_set_gauge_renders_grouped_by_name(self):
        set_gauge("db_pool_checkedout", 3)
        set_gauge("celery_queue_depth", 5, queue="agent.approval")
        out = render_metrics()
        self.assertIn("# TYPE loom_db_pool_checkedout gauge", out)
        self.assertIn("loom_db_pool_checkedout 3", out)
        self.assertIn("# TYPE loom_celery_queue_depth gauge", out)
        self.assertIn('loom_celery_queue_depth{queue="agent.approval"} 5', out)

    def test_sse_open_close_pair(self):
        """SSE 计数 opened/closed 严格配对：两次 opened + 一次 closed 余 1，归零后 gauge=0。"""
        sse_connection_opened("agent")
        sse_connection_opened("agent")
        sse_connection_closed("agent")
        try:
            self.assertIn('loom_sse_connections_active{endpoint="agent"} 1', render_metrics())
        finally:
            sse_connection_closed("agent")
        self.assertIn('loom_sse_connections_active{endpoint="agent"} 0', render_metrics())


class QueueDepthGaugeTestCase(unittest.TestCase):
    def test_collect_runtime_gauges_sets_pool_anyio_queue_depth(self):
        """采集口径：ΣLLEN(优先级键) 按队列聚合 + unacked 单列 + 池/线程池水位。"""
        from main import _collect_runtime_gauges

        queue_count = 12
        width = _kombu_suffix_count()
        results = [index for index in range(queue_count * width)] + [77]
        fake_client = MagicMock()
        fake_client.pipeline.return_value.execute.return_value = results

        fake_app = MagicMock()
        fake_queues = []
        for index in range(queue_count):
            queue = MagicMock()
            queue.name = f"q{index}"
            fake_queues.append(queue)
        fake_app.conf.task_queues = fake_queues

        pool = MagicMock()
        pool.checkedout.return_value = 4
        pool.overflow.return_value = 1
        limiter = MagicMock()
        limiter.total_tokens = 100
        limiter.borrowed_tokens = 7
        limiter.statistics.return_value = SimpleNamespace(tasks_waiting=2)

        metrics_module._gauges.clear()
        self.addCleanup(metrics_module._gauges.clear)
        with (
            patch("main.engine") as fake_engine,
            patch("anyio.to_thread.current_default_thread_limiter", return_value=limiter),
            patch("app.celery_app.celery_app", fake_app),
            patch("app.modules.base.service.cache_service.get_redis_client", return_value=fake_client),
        ):
            fake_engine.pool = pool
            _collect_runtime_gauges()

        self.assertEqual(metrics_module._gauges[("db_pool_checkedout", ())], 4)
        self.assertEqual(metrics_module._gauges[("db_pool_overflow", ())], 1)
        self.assertEqual(metrics_module._gauges[("thread_pool_total", ())], 100.0)
        self.assertEqual(metrics_module._gauges[("thread_pool_borrowed", ())], 7.0)
        self.assertEqual(metrics_module._gauges[("thread_pool_tasks_waiting", ())], 2)
        # q0 的四条优先级键 = results[0:4] = 0+1+2+3
        self.assertEqual(metrics_module._gauges[("celery_queue_depth", (("queue", "q0"),))], 6)
        self.assertEqual(metrics_module._gauges[("celery_unacked_total", ())], 77.0)


if __name__ == "__main__":
    unittest.main()
