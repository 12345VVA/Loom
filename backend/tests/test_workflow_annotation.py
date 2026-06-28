"""人工标注 + Cohen's κ judge 校准测试（P1-4）。"""

from __future__ import annotations

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow_annotation.model.annotation import WorkflowAnnotation
from app.modules.workflow_annotation.service.annotation_service import (
    _kappa_level,
    _label_to_bool,
    cohen_kappa,
)
from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun


class CohenKappaTestCase(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertEqual(cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]), 1.0)

    def test_no_agreement_negative(self):
        k = cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1])  # 完全相反
        self.assertLess(k, 0)

    def test_empty_returns_none(self):
        self.assertIsNone(cohen_kappa([], []))

    def test_partial_in_range(self):
        k = cohen_kappa([1, 1, 1, 0, 0, 0, 1, 0], [1, 0, 1, 0, 1, 0, 1, 0])
        self.assertIsInstance(k, float)
        self.assertGreaterEqual(k, -1.0)
        self.assertLessEqual(k, 1.0)

    def test_kappa_level(self):
        self.assertEqual(_kappa_level(0.8), "reliable")
        self.assertEqual(_kappa_level(0.5), "moderate")
        self.assertEqual(_kappa_level(0.2), "unreliable")
        self.assertEqual(_kappa_level(None), "no_annotation")


class LabelBoolTestCase(unittest.TestCase):
    def test_label_to_bool(self):
        self.assertEqual(_label_to_bool("pass"), 1)
        self.assertEqual(_label_to_bool("fail"), 0)
        self.assertEqual(_label_to_bool("PASS"), 1)


class ComputeKappaTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(WorkflowEvalRun(test_set_id=1, definition_id=1, status=EvalRunStatus.SUCCEEDED))
        self.session.commit()
        for i, passed in enumerate([True, True, False, False]):
            self.session.add(
                WorkflowEvalCaseResult(
                    eval_run_id=1,
                    case_key=f"c{i}",
                    score=1.0 if passed else 0.0,
                    passed=passed,
                    latency_ms=10,
                    status=CaseResultStatus.SUCCESS if passed else CaseResultStatus.FAIL,
                )
            )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_compute_kappa_gold_perfect(self):
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        for cr_id, label in zip([1, 2, 3, 4], ["pass", "pass", "fail", "fail"]):
            self.session.add(
                WorkflowAnnotation(case_result_id=cr_id, label=label, is_gold=True, annotator_user_id=1)
            )
        self.session.commit()
        result = WorkflowAnnotationService(self.session).compute_kappa(1)
        self.assertEqual(result["kappa"], 1.0)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["level"], "reliable")
        # summary_payload 已回填
        run = self.session.get(WorkflowEvalRun, 1)
        self.assertIn("judge_calibration", run.summary_payload)

    def test_compute_kappa_no_annotation(self):
        from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService

        result = WorkflowAnnotationService(self.session).compute_kappa(1)
        self.assertIsNone(result["kappa"])
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["level"], "no_annotation")


if __name__ == "__main__":
    unittest.main()
