"""T2 统计聚合改造测试：SQL 聚合正确性 + Redis 缓存命中/失效 + 各分组维度。

验证 summary() 在改为 func.count/sum/avg/case 聚合后，关键指标与原 Python 聚合一致，
且 CacheNamespace 缓存能命中并在 invalidate_summary_cache 后失效。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.ai.model.ai import AiModelCallLog
from app.modules.ai.service.stats_service import (
    AiModelCallStatsService,
    invalidate_summary_cache,
)


class StatsAggregationTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        invalidate_summary_cache()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        invalidate_summary_cache()

    def _add_log(self, **kwargs):
        defaults = {
            "status": "success",
            "latency_ms": 100,
            "total_tokens": 10,
            "cost_micro_usd": 1000,
            "model_type": "chat",
            "created_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        self.session.add(AiModelCallLog(**defaults))

    def test_summary_totals(self):
        self._add_log(status="success", latency_ms=100, total_tokens=10, cost_micro_usd=1000)
        self._add_log(status="success", latency_ms=200, total_tokens=20, cost_micro_usd=2000)
        self._add_log(status="error", latency_ms=300, total_tokens=0, cost_micro_usd=0)
        self.session.commit()
        invalidate_summary_cache()

        result = AiModelCallStatsService(self.session).summary(days=None)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["error"], 1)
        self.assertEqual(result["totalTokens"], 30)
        self.assertEqual(result["costMicroUsd"], 3000)
        self.assertEqual(result["avgLatencyMs"], 200)  # (100+200+300)/3
        self.assertEqual(result["successRate"], round(2 / 3, 4))

    def test_group_by_user(self):
        self._add_log(user_id=1, status="success")
        self._add_log(user_id=1, status="error")
        self._add_log(user_id=2, status="success")
        self._add_log(user_id=None, status="success")  # 归入 user:-
        self.session.commit()
        invalidate_summary_cache()

        result = AiModelCallStatsService(self.session).summary(days=None, group_by="user")
        keys = {g["key"] for g in result["groups"]}
        self.assertEqual(keys, {"user:1", "user:2", "user:-"})

        u1 = next(g for g in result["groups"] if g["key"] == "user:1")
        self.assertEqual(u1["total"], 2)
        self.assertEqual(u1["success"], 1)
        self.assertEqual(u1["error"], 1)
        self.assertEqual(u1["userId"], 1)

    def test_group_by_model(self):
        self._add_log(model_id=10)
        self._add_log(model_id=20)
        self.session.commit()
        invalidate_summary_cache()

        result = AiModelCallStatsService(self.session).summary(days=None, group_by="model")
        model_ids = {g["modelId"] for g in result["groups"]}
        self.assertEqual(model_ids, {10, 20})

    def test_day_grouping_key_format(self):
        self._add_log(created_at=datetime(2026, 6, 25, 10, 0, 0))
        self._add_log(created_at=datetime(2026, 6, 25, 23, 0, 0))
        self._add_log(created_at=datetime(2026, 6, 24, 10, 0, 0))
        self.session.commit()
        invalidate_summary_cache()

        result = AiModelCallStatsService(self.session).summary(days=None, group_by="day")
        keys = {g["key"] for g in result["groups"]}
        # 同日两条归并为一组，key 为 YYYY-MM-DD 字符串
        self.assertEqual(keys, {"2026-06-25", "2026-06-24"})
        day_25 = next(g for g in result["groups"] if g["key"] == "2026-06-25")
        self.assertEqual(day_25["total"], 2)

    def test_days_filter(self):
        self._add_log(created_at=datetime.utcnow())
        self._add_log(created_at=datetime(2020, 1, 1))  # 远早于任何 days 窗口
        self.session.commit()
        invalidate_summary_cache()

        result = AiModelCallStatsService(self.session).summary(days=7)
        self.assertEqual(result["total"], 1)  # 只统计近 7 天

    def test_cache_hit_and_invalidate(self):
        self._add_log(status="success")
        self.session.commit()
        invalidate_summary_cache()

        svc = AiModelCallStatsService(self.session)
        r1 = svc.summary(days=None)
        self.assertEqual(r1["total"], 1)

        # 再插一条但不失效缓存 → 第二次应命中缓存，total 仍为旧值
        self._add_log(status="success")
        self.session.commit()
        r2 = svc.summary(days=None)
        self.assertEqual(r2["total"], 1)

        # 失效后重新聚合 → 反映新增
        invalidate_summary_cache()
        r3 = svc.summary(days=None)
        self.assertEqual(r3["total"], 2)

    def test_cleanup_invalidates_summary_cache(self):
        """清理任务删除调用日志后应失效看板缓存，否则看板短时陈旧（与 _log_call 失效对齐）。"""
        from app.modules.ai.service.cleanup_service import AiGovernanceCleanupService

        self._add_log(status="success", created_at=datetime(2020, 1, 1))  # 老日志，会被清理
        self._add_log(status="success")  # 新日志
        self.session.commit()
        invalidate_summary_cache()

        svc = AiModelCallStatsService(self.session)
        self.assertEqual(svc.summary(days=None)["total"], 2)

        # 跑清理：删除 180 天前的调用日志后应失效缓存
        AiGovernanceCleanupService(self.session).clean(call_log_keep_days=180)

        # 缓存被失效 → 重新聚合反映删除（否则会命中缓存仍为 2）
        self.assertEqual(svc.summary(days=None)["total"], 1)

    def test_empty_returns_zero_totals(self):
        invalidate_summary_cache()
        result = AiModelCallStatsService(self.session).summary(days=None)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["successRate"], 0)
        self.assertEqual(result["avgLatencyMs"], 0)
        self.assertEqual(result["groups"], [])


if __name__ == "__main__":
    unittest.main()
