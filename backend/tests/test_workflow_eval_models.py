"""T9a 评价系统数据模型测试：4 表建表、CRUD、M1 补建的复合索引。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core import database as db_module
from app.core.database import _ensure_indexes
from app.modules.workflow_eval.model import (
    WorkflowEvalCaseResult,
    WorkflowEvalRun,
    WorkflowTestCase,
    WorkflowTestSet,
)
from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus


class WorkflowEvalModelsTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_tables_created(self):
        names = set(inspect(self.engine).get_table_names())
        for table in (
            "workflow_eval_test_set",
            "workflow_eval_test_case",
            "workflow_eval_run",
            "workflow_eval_case_result",
        ):
            self.assertIn(table, names)

    def test_create_test_set_and_cases(self):
        with Session(self.engine) as s:
            ts = WorkflowTestSet(name="ts1", definition_id=1, items_count=2, user_id=1)
            s.add(ts)
            s.commit()
            s.refresh(ts)
            s.add(WorkflowTestCase(test_set_id=ts.id, case_key="c1", input_data='{"q":"hi"}', sort_order=0))
            s.add(WorkflowTestCase(test_set_id=ts.id, case_key="c2", input_data='{"q":"yo"}', sort_order=1))
            s.commit()
            cases = s.exec(select(WorkflowTestCase).where(WorkflowTestCase.test_set_id == ts.id)).all()
            self.assertEqual(len(cases), 2)

    def test_create_run_and_case_results(self):
        with Session(self.engine) as s:
            run = WorkflowEvalRun(
                test_set_id=1, definition_id=1, status=EvalRunStatus.RUNNING,
                total=2, passed=1, p95_latency_ms=200, user_id=1,
            )
            s.add(run)
            s.commit()
            s.refresh(run)
            s.add(WorkflowEvalCaseResult(
                eval_run_id=run.id, case_key="c1", score=1.0, passed=True,
                latency_ms=100, status=CaseResultStatus.SUCCESS,
            ))
            s.add(WorkflowEvalCaseResult(
                eval_run_id=run.id, case_key="c2", score=0.2, passed=False,
                latency_ms=200, status=CaseResultStatus.FAIL,
            ))
            s.commit()
            results = s.exec(
                select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == run.id)
            ).all()
            self.assertEqual(len(results), 2)

    def test_eval_indexes_created_by_ensure_indexes(self):
        """M1 补索引机制为评价表建回归/P95 复合索引。"""
        with patch.object(db_module, "engine", self.engine):
            _ensure_indexes()

        case_result_indexes = {
            ix["name"] for ix in inspect(self.engine).get_indexes("workflow_eval_case_result") if ix.get("name")
        }
        self.assertIn("ix_workflow_eval_case_result_eval_run_id_latency_ms", case_result_indexes)
        self.assertIn("ix_workflow_eval_case_result_eval_run_id_case_key", case_result_indexes)

        run_indexes = {
            ix["name"] for ix in inspect(self.engine).get_indexes("workflow_eval_run") if ix.get("name")
        }
        self.assertIn("ix_workflow_eval_run_test_set_id_created_at", run_indexes)


if __name__ == "__main__":
    unittest.main()
