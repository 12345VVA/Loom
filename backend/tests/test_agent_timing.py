"""agent 全链路耗时打点（timing）与 SSE 终态必达回归。

- timed CM：正常退出按 level 记录（extra 全字段透传）、异常退出记 ERROR 后原样抛出、
  达到 slow 阈值升级 WARN；
- _execute_run 终态必达外圈：前置段（engine/Session/db.get）异常时 handle 仍收到
  error 终态帧 + None 哨兵（此前 worker 线程直接死掉，generator 无限心跳、前端永等）。
"""

from __future__ import annotations

import logging
import time
import unittest
from unittest import mock

from helpers import make_test_engine

from app.core.config import settings
from app.modules.agent.model.agent import AgentMessage, AgentRunTrace, AgentSession
from app.modules.agent.service.runtime.run_service import AgentRunService, RunDeadline, RunHandle
from app.modules.agent.service.runtime.timing import logger as timing_logger
from app.modules.agent.service.runtime.timing import timed

_TIMING_TABLES = [AgentRunTrace.__table__, AgentSession.__table__, AgentMessage.__table__]


class TimedContextManagerTests(unittest.TestCase):
    def test_normal_exit_logs_at_level_with_extra(self) -> None:
        with self.assertLogs(timing_logger, level="INFO") as captured:
            with timed("llm.round", level=logging.INFO, trace_token="tok-1") as bag:
                bag["round"] = 3
        record = captured.records[0]
        self.assertEqual(record.levelno, logging.INFO)
        self.assertEqual(record.phase, "llm.round")
        self.assertEqual(record.status, "ok")
        self.assertEqual(record.round, 3)
        self.assertEqual(record.trace_token, "tok-1")
        self.assertIsInstance(record.duration_ms, int)

    def test_exception_exit_logs_error_and_reraises(self) -> None:
        with self.assertLogs(timing_logger, level="ERROR") as captured:
            with self.assertRaises(ValueError):
                with timed("worker.wiring", trace_token="tok-2"):
                    raise ValueError("装配炸了")
        record = captured.records[0]
        self.assertEqual(record.status, "error")
        self.assertEqual(record.error_type, "ValueError")
        self.assertEqual(record.phase, "worker.wiring")

    def test_slow_call_escalates_to_warning(self) -> None:
        with mock.patch.object(settings, "AGENT_TIMING_SLOW_MODEL_MS", 1):
            with self.assertLogs(timing_logger, level="WARNING") as captured:
                with timed("llm.round", level=logging.INFO, slow="model"):
                    time.sleep(0.005)  # 5ms >= 1ms 阈值
        self.assertEqual(captured.records[0].levelno, logging.WARNING)
        self.assertEqual(captured.records[0].phase, "llm.round")

    def test_fast_call_stays_at_configured_level(self) -> None:
        with mock.patch.object(settings, "AGENT_TIMING_SLOW_MODEL_MS", 3_600_000):
            with self.assertLogs(timing_logger, level="INFO") as captured:
                with timed("llm.round", level=logging.INFO, slow="model"):
                    pass
        self.assertEqual(captured.records[0].levelno, logging.INFO)


class TerminalGuaranteeTests(unittest.TestCase):
    """终态必达外圈：前置段异常（trace 不存在 → wiring 内 AttributeError）也必须收到 error 帧。"""

    def setUp(self) -> None:
        self.engine = make_test_engine(tables=_TIMING_TABLES)

    def _make_handle(self) -> RunHandle:
        return RunHandle(
            trace_id=0,
            trace_token="guarantee-token",
            session_id=1,
            deadline=RunDeadline(5),
        )

    def test_precondition_failure_still_closes_with_error(self) -> None:
        service = AgentRunService.__new__(AgentRunService)  # 不触发基类构造（测试只走 _execute_run）
        handle = self._make_handle()
        job = {
            "handle": handle,
            "engine": self.engine,  # 工作线程注入引擎
            "trace_id": 999,  # 不存在 → trace=None → wiring 段 AttributeError
            "session_id": 1,
            "payload": {"execution_mode": "chat"},
            "user": {"id": 1, "name": "tester", "is_super_admin": True},
        }

        with self.assertLogs("agent.run_service", level="ERROR"):
            service._execute_run(job)

        events = []
        while True:
            event = handle.event_queue.get(timeout=2)
            if event is None:
                break
            events.append(event)
        types = [e.type for e in events]
        self.assertEqual(types[-1], "error")  # 终态帧必达（修复前：队列空、generator 无限心跳）
        self.assertIn("运行异常终止", events[-1].payload.get("message", ""))


if __name__ == "__main__":
    unittest.main()
