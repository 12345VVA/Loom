"""T4/T5 执行体批量落库测试：_persist_node_payloads_sync / _is_cancelled_sync / _flush_worker。

验证节点日志经 asyncio.Queue + 后台 flush_worker 批量 commit 的正确性，
以及脱敏 payload 直接入库（audit S2 不削弱）、cancelled 实例跳过推进度更新。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.tasks.workflow_tasks import (
    _FLUSH_SENTINEL,
    _flush_worker,
    _is_cancelled_sync,
    _persist_node_payloads_sync,
)


def _payload(node_id: str, latency: int = 10) -> dict:
    return {
        "node_id": node_id,
        "node_name": node_id.upper(),
        "node_type": "llm",
        "state_data": '{"v": 1}',
        "input_data": '{"in": "masked"}',
        "output_data": '{"out": "masked"}',
        "latency_ms": latency,
    }


class FlushPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            inst = WorkflowInstance(definition_id=1, thread_id="t1", status="running", state_data="{}")
            s.add(inst)
            s.commit()
            s.refresh(inst)
            self.instance_id = inst.id

    def tearDown(self):
        self.engine.dispose()

    def _logs_count(self) -> int:
        with Session(self.engine) as s:
            return len(s.exec(select(WorkflowExecutionLog)).all())

    def test_persist_writes_logs_and_advances_current_node(self):
        payloads = [_payload("n1", 10), _payload("n2", 20)]
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
            _persist_node_payloads_sync(self.instance_id, payloads)

        self.assertEqual(self._logs_count(), 2)
        with Session(self.engine) as s:
            inst = s.get(WorkflowInstance, self.instance_id)
            self.assertEqual(inst.current_node, "n2")  # 最后一个 payload 的推进
            self.assertEqual(inst.state_data, '{"v": 1}')

    def test_cancelled_instance_skips_progress_update_but_still_logs(self):
        with Session(self.engine) as s:
            inst = s.get(WorkflowInstance, self.instance_id)
            inst.status = "cancelled"
            s.add(inst)
            s.commit()

        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
            _persist_node_payloads_sync(self.instance_id, [_payload("n3")])

        # exec_log 仍写入（节点确实执行过），但 instance.current_node 不被覆盖
        self.assertEqual(self._logs_count(), 1)
        with Session(self.engine) as s:
            inst = s.get(WorkflowInstance, self.instance_id)
            self.assertIsNone(inst.current_node)

    def test_empty_payloads_noop(self):
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
            _persist_node_payloads_sync(self.instance_id, [])
        self.assertEqual(self._logs_count(), 0)

    def test_is_cancelled_sync(self):
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
            self.assertFalse(_is_cancelled_sync(self.instance_id))
        with Session(self.engine) as s:
            inst = s.get(WorkflowInstance, self.instance_id)
            inst.status = "cancelled"
            s.add(inst)
            s.commit()
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
            self.assertTrue(_is_cancelled_sync(self.instance_id))


class FlushWorkerTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            inst = WorkflowInstance(definition_id=1, thread_id="t1", status="running", state_data="{}")
            s.add(inst)
            s.commit()
            s.refresh(inst)
            self.instance_id = inst.id

    def tearDown(self):
        self.engine.dispose()

    def test_drain_flushes_remaining_batch(self):
        """投入 < batch_size 的 payload 后发 SENTINEL，flush_worker 应 flush 全部后退出。"""
        payloads = [_payload("n1"), _payload("n2"), _payload("n3")]

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            for p in payloads:
                await queue.put(p)
            await queue.put(_FLUSH_SENTINEL)
            with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
                await _flush_worker(self.instance_id, queue)

        asyncio.run(asyncio.wait_for(run(), timeout=5))

        with Session(self.engine) as s:
            logs = s.exec(select(WorkflowExecutionLog)).all()
        self.assertEqual(len(logs), 3)

    def test_batch_size_triggers_intermediate_flush(self):
        """投入 >= batch_size 的 payload 触发中途 flush，再 SENTINEL 收尾。"""

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            for i in range(12):  # 超过 _FLUSH_BATCH_SIZE(10)
                await queue.put(_payload(f"n{i}"))
            await queue.put(_FLUSH_SENTINEL)
            with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine):
                await _flush_worker(self.instance_id, queue)

        asyncio.run(asyncio.wait_for(run(), timeout=5))

        with Session(self.engine) as s:
            logs = s.exec(select(WorkflowExecutionLog)).all()
        self.assertEqual(len(logs), 12)


if __name__ == "__main__":
    unittest.main()
