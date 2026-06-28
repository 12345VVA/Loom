"""T6+T8 日志存储优化测试：offload/resolve 往返、ref_prev 引用还原、协调、向后兼容。

用 mock storage（内存 dict）模拟对象存储，patch engine 用内存 SQLite。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.framework.storage import offload_payload, resolve_payload
from app.modules.workflow.controller.admin.instance import _restore_logs_payload
from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.tasks.workflow_tasks import _persist_node_payloads_sync

_FAKE_STORE: dict[str, bytes] = {}


def _make_mock_storage() -> MagicMock:
    m = MagicMock()

    def save(file_content: bytes, filename: str) -> str:
        key = f"fake://{filename}"
        _FAKE_STORE[key] = file_content
        return key

    def read(path: str) -> bytes:
        return _FAKE_STORE[path]

    m.save.side_effect = save
    m.read.side_effect = read
    return m


def _payload(node_id: str, input_data: str, output_data: str) -> dict:
    return {
        "node_id": node_id,
        "node_name": node_id.upper(),
        "node_type": "llm",
        "state_data": output_data,
        "input_data": input_data,
        "output_data": output_data,
        "latency_ms": 10,
    }


class StorageOptimizationTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        _FAKE_STORE.clear()
        with Session(self.engine) as s:
            s.add(WorkflowInstance(definition_id=1, thread_id="t1", status="running", state_data="{}"))
            s.commit()

    def tearDown(self):
        self.engine.dispose()
        _FAKE_STORE.clear()

    def test_offload_below_threshold_inline(self):
        with patch("app.framework.storage.StorageService.get_instance", return_value=_make_mock_storage()), \
                patch.object(settings, "PAYLOAD_STORAGE_THRESHOLD", 100):
            inline, ref = offload_payload("abc")
        self.assertEqual((inline, ref), ("abc", None))

    def test_offload_above_threshold_roundtrip(self):
        big = "x" * 500
        with patch("app.framework.storage.StorageService.get_instance", return_value=_make_mock_storage()), \
                patch.object(settings, "PAYLOAD_STORAGE_THRESHOLD", 100):
            inline, ref = offload_payload(big)
            self.assertEqual(inline, "")
            self.assertIsNotNone(ref)
            self.assertEqual(resolve_payload(inline, ref), big)  # 读回一致

    def test_persist_ref_prev_and_restore(self):
        payloads = [
            _payload("n1", '{"init":1}', '{"v":1}'),
            _payload("n2", '{"v":1}', '{"v":2}'),  # n2.input == n1.output（冗余）
        ]
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine), \
                patch("app.framework.storage.StorageService.get_instance", return_value=_make_mock_storage()), \
                patch.object(settings, "PAYLOAD_STORAGE_THRESHOLD", 10 * 1024 * 1024):  # 大阈值，不 offload
            _persist_node_payloads_sync(1, payloads)

        with Session(self.engine) as s:
            logs = list(s.exec(
                select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == 1).order_by(WorkflowExecutionLog.id)
            ).all())
            self.assertEqual(len(logs), 2)
            # 首条 full
            self.assertEqual(logs[0].payload_type, "full")
            self.assertEqual(logs[0].input_data, '{"init":1}')
            self.assertEqual(logs[0].diff_base_log_id, None)
            # 第二条 ref_prev
            self.assertEqual(logs[1].payload_type, "ref_prev")
            self.assertEqual(logs[1].input_data, "REF_PREV")
            self.assertEqual(logs[1].diff_base_log_id, logs[0].id)
            # 还原：ref_prev input 用前条 output 填充
            _restore_logs_payload(logs)
            self.assertEqual(logs[1].input_data, logs[0].output_data)

    def test_coordination_big_output_with_ref_prev_input(self):
        big_output = '{"v":1,"big":"' + "x" * 1000 + '"}'
        payloads = [
            _payload("n1", '{"init":1}', big_output),  # output 大 → offload
            _payload("n2", big_output, '{"v":2}'),  # input == 上条 output，ref_prev
        ]
        with patch("app.modules.workflow.tasks.workflow_tasks.engine", self.engine), \
                patch("app.framework.storage.StorageService.get_instance", return_value=_make_mock_storage()), \
                patch.object(settings, "PAYLOAD_STORAGE_THRESHOLD", 100):  # 小阈值，big_output 触发 offload
            _persist_node_payloads_sync(1, payloads)
            with Session(self.engine) as s:
                logs = list(s.exec(
                    select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == 1).order_by(WorkflowExecutionLog.id)
                ).all())
                # n1 output 大 → 分离
                self.assertEqual(logs[0].output_data, "")
                self.assertIsNotNone(logs[0].output_storage_ref)
                # n2 input ref_prev（不存内容，无 storage_ref）
                self.assertEqual(logs[1].payload_type, "ref_prev")
                self.assertIsNone(logs[1].input_storage_ref)
                # 协调还原（在 patch 内，storage.read 走 mock）
                _restore_logs_payload(logs)
                self.assertEqual(logs[0].output_data, big_output)
                self.assertEqual(logs[1].input_data, big_output)

    def test_backward_compat_legacy_log(self):
        """旧 log（payload_type 默认 full、无 storage_ref、input/output 内联）还原后原样。"""
        with Session(self.engine) as s:
            s.add(WorkflowExecutionLog(
                instance_id=1, node_id="legacy", node_name="L", node_type="llm",
                input_data='{"old":1}', output_data='{"old":2}', latency_ms=5, status="success",
            ))
            s.commit()
        with Session(self.engine) as s:
            logs = list(s.exec(select(WorkflowExecutionLog)).all())
            _restore_logs_payload(logs)
            self.assertEqual(logs[0].input_data, '{"old":1}')
            self.assertEqual(logs[0].output_data, '{"old":2}')


if __name__ == "__main__":
    unittest.main()
