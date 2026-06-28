"""T7 logs 接口增量/分页测试：since_log_id + limit 查询行为。

验证 /logs 接口新增的增量（sinceLogId）与分页（limit）参数的 SQL 行为正确，
不传时保持全量向后兼容。复合索引 (instance_id, created_at) 由 M1 补建。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance

_BASE = datetime(2026, 6, 25, 10, 0, 0)


def _build_logs_query(instance_id: int, since_log_id: int | None, limit: int | None):
    """复现 WorkflowInstanceController.get_logs 的查询构造逻辑。"""
    stmt = select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == instance_id)
    if since_log_id is not None:
        stmt = stmt.where(WorkflowExecutionLog.id > since_log_id)
    stmt = stmt.order_by(WorkflowExecutionLog.created_at.asc(), WorkflowExecutionLog.id.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


class LogsIncrementalTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add(WorkflowInstance(definition_id=1, thread_id="t1", status="success", state_data="{}", user_id=1))
            s.commit()
        # 5 条日志，created_at 严格递增（与 id 同序）
        with Session(self.engine) as s:
            for i in range(5):
                s.add(
                    WorkflowExecutionLog(
                        instance_id=1,
                        node_id=f"n{i + 1}",
                        node_name=f"N{i + 1}",
                        node_type="llm",
                        input_data="{}",
                        output_data="{}",
                        latency_ms=(i + 1) * 10,
                        status="success",
                        created_at=_BASE + timedelta(seconds=i),
                    )
                )
            s.commit()

    def tearDown(self):
        self.engine.dispose()

    def _exec(self, since, limit):
        with Session(self.engine) as s:
            return list(s.exec(_build_logs_query(1, since, limit)).all())

    def test_full_set_when_no_params(self):
        logs = self._exec(None, None)
        self.assertEqual([l.node_id for l in logs], ["n1", "n2", "n3", "n4", "n5"])

    def test_since_returns_only_newer(self):
        # 取前两条的最大 id，增量应返回 n3..n5
        first_two = self._exec(None, 2)
        since_id = max(l.id for l in first_two)
        logs = self._exec(since_id, None)
        self.assertEqual([l.node_id for l in logs], ["n3", "n4", "n5"])

    def test_since_with_limit(self):
        first_two = self._exec(None, 2)
        since_id = max(l.id for l in first_two)
        logs = self._exec(since_id, 2)
        self.assertEqual([l.node_id for l in logs], ["n3", "n4"])

    def test_limit_only(self):
        logs = self._exec(None, 3)
        self.assertEqual([l.node_id for l in logs], ["n1", "n2", "n3"])


if __name__ == "__main__":
    unittest.main()
