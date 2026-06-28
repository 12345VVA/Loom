"""T9d 回归对比测试：按 case_key 对齐、退化/改善识别、不同测试集拒绝。"""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.service.regression import compare_runs


class RegressionTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        # run_a(id=1, ts=1): c1=0.9, c2=0.5, c3=0.8
        # run_b(id=2, ts=1): c1=0.7(退化), c2=0.9(改善), c4=0.6(新增)
        # run_c(id=3, ts=2): 不同测试集
        with Session(self.engine) as s:
            s.add(WorkflowEvalRun(test_set_id=1, status=EvalRunStatus.SUCCEEDED, version_label="a", avg_score=0.73, pass_rate=0.66, p95_latency_ms=100, total_cost_micro_usd=1000))
            s.add(WorkflowEvalRun(test_set_id=1, status=EvalRunStatus.SUCCEEDED, version_label="b", avg_score=0.73, pass_rate=0.66, p95_latency_ms=120, total_cost_micro_usd=1200))
            s.add(WorkflowEvalRun(test_set_id=2, status=EvalRunStatus.SUCCEEDED, version_label="c"))
            s.commit()
            for run_id, items in {
                1: [("c1", 0.9), ("c2", 0.5), ("c3", 0.8)],
                2: [("c1", 0.7), ("c2", 0.9), ("c4", 0.6)],
            }.items():
                for key, score in items:
                    s.add(WorkflowEvalCaseResult(
                        eval_run_id=run_id, case_key=key, score=score,
                        passed=score >= 0.6, latency_ms=100, status=CaseResultStatus.SUCCESS,
                    ))
            s.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_compare_same_test_set(self):
        with Session(self.engine) as s:
            result = compare_runs(s, 1, 2)
        self.assertEqual(result["onlyA"], ["c3"])
        self.assertEqual(result["onlyB"], ["c4"])
        self.assertEqual(result["common"], ["c1", "c2"])
        self.assertEqual([r["caseKey"] for r in result["regressed"]], ["c1"])  # 0.7-0.9=-0.2
        self.assertEqual([r["caseKey"] for r in result["improved"]], ["c2"])  # 0.9-0.5=+0.4
        # 指标 diff（b 相对 a）
        self.assertEqual(result["metricsDiff"]["p95LatencyMs"], 20)
        self.assertEqual(result["metricsDiff"]["totalCostMicroUsd"], 200)

    def test_compare_different_test_set_rejected(self):
        with Session(self.engine) as s:
            with self.assertRaises(HTTPException) as cm:
                compare_runs(s, 1, 3)
        self.assertEqual(cm.exception.status_code, 400)

    def test_compare_missing_run(self):
        with Session(self.engine) as s:
            with self.assertRaises(HTTPException):
                compare_runs(s, 1, 999)

    def test_compare_non_terminal_rejected(self):
        """未完成的运行不能参与回归对比。"""
        with Session(self.engine) as s:
            s.add(WorkflowEvalRun(test_set_id=1, status=EvalRunStatus.RUNNING, version_label="r"))
            s.commit()
            with self.assertRaises(HTTPException) as cm:
                compare_runs(s, 1, 4)
            self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
