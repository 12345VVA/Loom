"""trace 级评估测试（P1-1）：节点日志读取还原 + 节点评估器。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow_eval.service.eval_orchestrator import (
    _load_node_io,
    evaluate_node_evaluators,
)


class TraceTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(WorkflowInstance(definition_id=1, thread_id="t1", status="success"))
        self.session.add(
            WorkflowExecutionLog(
                instance_id=1,
                node_id="llm1",
                node_name="N1",
                node_type="llm",
                input_data='{"q":"hi"}',
                output_data='{"answer":"hello world"}',
                payload_type="full",
                latency_ms=100,
                status="success",
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_load_node_io_full_payload(self):
        io = _load_node_io(self.session, 1)
        self.assertIn("llm1", io)
        self.assertEqual(io["llm1"]["input"], {"q": "hi"})
        self.assertEqual(io["llm1"]["output"], {"answer": "hello world"})
        self.assertEqual(io["llm1"]["node_type"], "llm")

    def test_evaluate_node_rule_match_pass(self):
        node_evaluators = {
            "llm1": {"type": "rule_match", "config": {"mode": "contains"}, "expected_text": "hello"}
        }
        with patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            results = evaluate_node_evaluators(1, node_evaluators, {})
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["passed"])
        self.assertEqual(results[0]["node_id"], "llm1")
        self.assertEqual(results[0]["node_type"], "llm")

    def test_evaluate_node_rule_match_fail(self):
        node_evaluators = {
            "llm1": {"type": "rule_match", "config": {"mode": "contains"}, "expected_text": "NONEXISTENT"}
        }
        with patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            results = evaluate_node_evaluators(1, node_evaluators, {})
        self.assertFalse(results[0]["passed"])

    def test_evaluate_node_not_found(self):
        node_evaluators = {
            "missing": {"type": "rule_match", "config": {"mode": "contains"}, "expected_text": "x"}
        }
        with patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            results = evaluate_node_evaluators(1, node_evaluators, {})
        self.assertFalse(results[0]["passed"])
        self.assertIn("未找到", results[0]["reason"])


if __name__ == "__main__":
    unittest.main()
