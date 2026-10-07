"""T4/T5 执行体批量落库测试：_persist_node_payloads_sync / _is_cancelled_sync / _flush_worker。

验证节点日志经 asyncio.Queue + 后台 flush_worker 批量 commit 的正确性，
以及脱敏 payload 直接入库（audit S2 不削弱）、cancelled 实例跳过推进度更新。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.tasks.workflow_tasks import (
    _FLUSH_SENTINEL,
    _drain_flush,
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
        self.engine = make_test_engine()
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
        self.engine = make_test_engine()
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
                await _flush_worker(self.instance_id, queue, {"errors": 0, "dropped": 0})

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
                await _flush_worker(self.instance_id, queue, {"errors": 0, "dropped": 0})

        asyncio.run(asyncio.wait_for(run(), timeout=5))

        with Session(self.engine) as s:
            logs = s.exec(select(WorkflowExecutionLog)).all()
        self.assertEqual(len(logs), 12)


class FlushStatsTestCase(unittest.TestCase):
    """WF-P2-2：单批落库失败不阻断消费（协程存活），stats 累计并由 drain 汇总告警。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            inst = WorkflowInstance(definition_id=1, thread_id="t1", status="running", state_data="{}")
            s.add(inst)
            s.commit()
            s.refresh(inst)
            self.instance_id = inst.id

    def tearDown(self):
        self.engine.dispose()

    def test_batch_failure_does_not_block_consumption(self):
        """第一批落库失败（丢弃并计数），后续批次照常落库，协程存活到 SENTINEL。"""
        import app.modules.workflow.tasks.workflow_tasks as wt

        stats = {"errors": 0, "dropped": 0}
        real_persist = wt._persist_node_payloads_sync
        calls = {"n": 0}

        def flaky_persist(instance_id, payloads):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("db down")
            return real_persist(instance_id, payloads)

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            for i in range(12):  # 两批：第一批 10 条（失败），第二批 2 条（成功）
                await queue.put(_payload(f"n{i}"))
            await queue.put(_FLUSH_SENTINEL)
            with (
                patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
                patch.object(wt, "_persist_node_payloads_sync", side_effect=flaky_persist),
            ):
                await _flush_worker(self.instance_id, queue, stats)

        asyncio.run(asyncio.wait_for(run(), timeout=5))

        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["dropped"], 10)
        with Session(self.engine) as s:
            logs = s.exec(select(WorkflowExecutionLog)).all()
        self.assertEqual(len(logs), 2, "仅第二批成功落库")

    def test_drain_summarizes_errors(self):
        """drain 收尾时 stats 有错误则发汇总 warning。"""
        recorded = []

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            task = asyncio.create_task(_flush_worker(self.instance_id, queue, {"errors": 2, "dropped": 7}))
            with patch(
                "app.modules.workflow.tasks.workflow_tasks.logger.warning",
                side_effect=lambda msg, *a: recorded.append(msg % a if a else msg),
            ):
                await _drain_flush(queue, task, self.instance_id, {"errors": 2, "dropped": 7})

        asyncio.run(asyncio.wait_for(run(), timeout=5))
        self.assertTrue(any("flush 收尾汇总" in r for r in recorded), f"应输出汇总告警: {recorded}")
        self.assertTrue(any("2" in r and "7" in r for r in recorded))

    def test_clean_run_has_no_warning(self):
        """全程成功：stats 全零、无汇总告警。"""
        recorded = []

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            stats = {"errors": 0, "dropped": 0}
            for i in range(12):
                await queue.put(_payload(f"n{i}"))
            await queue.put(_FLUSH_SENTINEL)
            with (
                patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine),
                patch(
                    "app.modules.workflow.tasks.workflow_tasks.logger.warning",
                    side_effect=lambda msg, *a: recorded.append(msg % a if a else msg),
                ),
            ):
                await _flush_worker(self.instance_id, queue, stats)
                await _drain_flush(queue, asyncio.create_task(asyncio.sleep(0)), self.instance_id, stats)

        asyncio.run(asyncio.wait_for(run(), timeout=5))
        self.assertTrue(all("flush 收尾汇总" not in r for r in recorded))
        with Session(self.engine) as s:
            logs = s.exec(select(WorkflowExecutionLog)).all()
        self.assertEqual(len(logs), 12)


if __name__ == "__main__":
    unittest.main()
