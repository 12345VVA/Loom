"""agent 假死 trace 兜底 sweep 测试（调用追踪审计 B3）。

覆盖：超宽限 running 终态化（failed + error 标注 + duration 补算）/ 新鲜 running 不动 /
waiting_approval 不扫（合法长等态）/ 条件更新幂等（重复 sweep 不重复处理）。
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from helpers import make_test_engine
from sqlmodel import Session

from app.modules.agent.model.agent import AgentRunTrace
from app.modules.agent.service.maintenance import sweep_stuck_traces


def _trace(**overrides) -> AgentRunTrace:
    fields = {
        "profile_id": 1,
        "run_mode": "published",
        "agent_code": "ag-t",
        "agent_name": "t",
        "session_id": 1,
        "user_id": 1,
        "status": "running",
    }
    fields.update(overrides)
    return AgentRunTrace(**fields)


def _backdate(session: Session, trace_id: int, minutes: int) -> None:
    """把 updated_at/created_at 回拨（E3 坑：BaseEntity.updated_at 的 default_factory
    覆盖显式传值，INSERT 造不出旧行——须 Core UPDATE 绕过 ORM 实例）。"""
    from sqlalchemy import update

    ts = datetime.now(UTC) - timedelta(minutes=minutes)
    session.execute(update(AgentRunTrace).where(AgentRunTrace.id == trace_id).values(updated_at=ts, created_at=ts))
    session.commit()


class SweepStuckTracesTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine(tables=[AgentRunTrace.__table__])
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_stale_running_is_finalized(self):
        """超宽限 running → failed + error 标注 + duration 按 created_at 补算。"""
        stale = _trace()
        self.session.add(stale)
        self.session.commit()
        _backdate(self.session, stale.id, minutes=45)

        swept = sweep_stuck_traces(self.session, grace_minutes=30)

        self.assertEqual(swept, [stale.id])
        row = self.session.get(AgentRunTrace, stale.id)
        self.assertEqual(row.status, "failed")
        self.assertIn("假死", row.error)
        self.assertIsNotNone(row.duration_ms)
        self.assertGreaterEqual(row.duration_ms, 40 * 60 * 1000 - 1000)

    def test_fresh_running_untouched(self):
        """宽限内 running 不动（防误杀慢 run）。"""
        fresh = _trace()
        self.session.add(fresh)
        self.session.commit()
        _backdate(self.session, fresh.id, minutes=5)

        swept = sweep_stuck_traces(self.session, grace_minutes=30)

        self.assertEqual(swept, [])
        self.assertEqual(self.session.get(AgentRunTrace, fresh.id).status, "running")

    def test_waiting_approval_not_swept(self):
        """waiting_approval 不扫——E4 解冻后审批是合法长等态（可等数日）。"""
        waiting = _trace(status="waiting_approval")
        self.session.add(waiting)
        self.session.commit()
        _backdate(self.session, waiting.id, minutes=48 * 60)

        swept = sweep_stuck_traces(self.session, grace_minutes=30)

        self.assertEqual(swept, [])
        self.assertEqual(self.session.get(AgentRunTrace, waiting.id).status, "waiting_approval")

    def test_idempotent_double_sweep(self):
        """条件更新幂等：首轮终态化后，二轮不再处理（并发/重复扫描安全）。"""
        stale = _trace()
        self.session.add(stale)
        self.session.commit()
        _backdate(self.session, stale.id, minutes=120)

        first = sweep_stuck_traces(self.session, grace_minutes=30)
        second = sweep_stuck_traces(self.session, grace_minutes=30)

        self.assertEqual(first, [stale.id])
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
