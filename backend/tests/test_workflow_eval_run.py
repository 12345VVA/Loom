"""T9c 批量评估执行测试：mock _async_execute，验证 case_result 落库、汇总指标、异常隔离。

不依赖真实 LangGraph——用 fake _async_execute 模拟执行（写 instance.state_data 含 workflow_output），
验证 _async_run_eval 的编排、评估、汇总、单 case 异常隔离。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus
from app.modules.workflow_eval.model.test_set import WorkflowTestCase, WorkflowTestSet
from app.modules.workflow_eval.service.eval_run_service import WorkflowEvalRunService
from app.modules.workflow_eval.tasks import eval_tasks
from fastapi import HTTPException


def _make_echo_execute(engine):
    """fake _async_execute：把 initial_vars.q 回写成 workflow_output='echo:{q}'，模拟成功执行。"""

    async def fake(instance_id, definition_id, initial_vars, resume_val=None, *, version_id=None, graph_json_override=None):
        with Session(engine) as s:
            inst = s.get(WorkflowInstance, instance_id)
            if inst:
                q = initial_vars.get("q", "") if isinstance(initial_vars, dict) else ""
                inst.state_data = json.dumps({"workflow_output": f"echo:{q}"})
                inst.status = "success"
                s.add(inst)
                s.commit()

    return fake


class EvalRunTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add(WorkflowDefinition(code="d1", name="D1", graph_json='{"nodes":[],"edges":[]}', user_id=1))
            s.add(WorkflowTestSet(name="ts1", definition_id=1, user_id=1, items_count=3))
            s.commit()
            s.add(WorkflowTestCase(test_set_id=1, case_key="c1", input_data='{"q":"hello"}', expected_text="echo:hello", sort_order=0))
            s.add(WorkflowTestCase(test_set_id=1, case_key="c2", input_data='{"q":"world"}', expected_text="echo:WRONG", sort_order=1))
            s.add(WorkflowTestCase(test_set_id=1, case_key="c3", input_data='{"q":""}', expected_text="echo:", sort_order=2))
            s.add(WorkflowEvalRun(
                test_set_id=1, definition_id=1, status=EvalRunStatus.PENDING,
                graph_json_snapshot='{"nodes":[],"edges":[]}', user_id=1,
            ))
            s.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_run_eval_writes_results_and_finalizes(self):
        with patch.object(eval_tasks, "_async_execute", _make_echo_execute(self.engine)), \
                patch.object(eval_tasks, "MAX_CONCURRENT_CASES", 1), \
                patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            asyncio.run(eval_tasks._async_run_eval(1, "task-id", "rule_match"))

        with Session(self.engine) as s:
            run = s.get(WorkflowEvalRun, 1)
            self.assertEqual(run.status, EvalRunStatus.SUCCEEDED)
            self.assertEqual(run.total, 3)
            self.assertEqual(run.passed, 2)
            self.assertEqual(run.failed, 1)
            self.assertEqual(run.errored, 0)
            self.assertEqual(run.avg_score, round(2 / 3, 4))
            self.assertEqual(run.pass_rate, round(2 / 3, 4))
            self.assertIsNotNone(run.finished_at)

            results = list(s.exec(
                select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == 1)
            ).all())
            self.assertEqual(len(results), 3)
            by_key = {r.case_key: r for r in results}
            self.assertEqual(by_key["c1"].status, CaseResultStatus.SUCCESS)
            self.assertEqual(by_key["c1"].score, 1.0)
            self.assertEqual(by_key["c2"].status, CaseResultStatus.FAIL)
            self.assertEqual(by_key["c2"].score, 0.0)
            self.assertEqual(by_key["c3"].status, CaseResultStatus.SUCCESS)
            # 方案 A：每个 case 关联了真实 instance（可回溯）
            self.assertIsNotNone(by_key["c1"].workflow_instance_id)

    def test_case_exception_isolated(self):
        """_async_execute 全部抛异常 → 每 case 写 error，整批不崩；全 error 时 run 为 FAILED（非 PARTIAL）。"""

        async def always_boom(instance_id, definition_id, initial_vars, resume_val=None, *, version_id=None, graph_json_override=None):
            raise RuntimeError("boom")

        with patch.object(eval_tasks, "_async_execute", always_boom), \
                patch.object(eval_tasks, "MAX_CONCURRENT_CASES", 1), \
                patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            asyncio.run(eval_tasks._async_run_eval(1, "task-id", "rule_match"))

        with Session(self.engine) as s:
            run = s.get(WorkflowEvalRun, 1)
            self.assertEqual(run.total, 3)
            self.assertEqual(run.errored, 3)
            # 全部用例异常（errored == total）→ FAILED，而非 PARTIAL
            self.assertEqual(run.status, EvalRunStatus.FAILED)
            errors = list(s.exec(
                select(WorkflowEvalCaseResult).where(
                    WorkflowEvalCaseResult.eval_run_id == 1,
                    WorkflowEvalCaseResult.status == CaseResultStatus.ERROR,
                )
            ).all())
            self.assertEqual(len(errors), 3)

    def test_missing_run_returns_early(self):
        with patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            # 不存在的 eval_run_id：不应抛异常
            asyncio.run(eval_tasks._async_run_eval(999, "task-id", "rule_match"))

    def test_mark_running_false_short_circuits(self):
        # mark_running 返回 False（已被取消）：_async_run_eval 早退，不跑 case、无 case_result
        fake_ctx = {
            "definition_id": 1,
            "graph_json_snapshot": {},
            "user_id": 1,
            "cases": [{"case_key": "c1", "input_data": "{}"}],
        }
        with patch.object(eval_tasks, "load_eval_context", return_value=fake_ctx), \
                patch.object(eval_tasks, "mark_running", return_value=False), \
                patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            asyncio.run(eval_tasks._async_run_eval(1, "task-id", "rule_match"))
        with Session(self.engine) as s:
            self.assertEqual(len(list(s.exec(select(WorkflowEvalCaseResult)).all())), 0)

    def test_list_cases_returns_camelcase(self):
        """list_cases 出口须为 camelCase（修复详情页字段取不到）。"""
        with patch.object(eval_tasks, "_async_execute", _make_echo_execute(self.engine)), \
                patch.object(eval_tasks, "MAX_CONCURRENT_CASES", 1), \
                patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            asyncio.run(eval_tasks._async_run_eval(1, "task-id", "rule_match"))
        with Session(self.engine) as s:
            res = WorkflowEvalRunService(s).list_cases(1)
        self.assertIn("list", res)
        item = res["list"][0]
        self.assertIn("caseKey", item)
        self.assertIn("actualOutput", item)
        self.assertIn("latencyMs", item)
        self.assertIn("status", item)
        self.assertNotIn("case_key", item)
        self.assertNotIn("actual_output", item)

    def test_assert_run_owned(self):
        """归属校验：owner 放行、非归属非超管 403、超管放行、不存在 404。"""
        from app.modules.workflow_eval.service.eval_run_service import _assert_run_owned

        class FakeUser:
            def __init__(self, uid: int, super_admin: bool):
                self.id = uid
                self.is_super_admin = super_admin

        with Session(self.engine) as s:
            # run id=1（setUp 建立时 user_id=1）
            _assert_run_owned(s, 1, FakeUser(1, False))  # owner
            with self.assertRaises(HTTPException) as cm:
                _assert_run_owned(s, 1, FakeUser(999, False))
            self.assertEqual(cm.exception.status_code, 403)
            _assert_run_owned(s, 1, FakeUser(999, True))  # 超管放行
            with self.assertRaises(HTTPException) as cm:
                _assert_run_owned(s, 999, None)
            self.assertEqual(cm.exception.status_code, 404)

    def test_load_eval_context_uses_snapshot_cases(self):
        """有快照时 load_eval_context 用快照 cases（不受当前用例改动影响）。"""
        from app.modules.workflow_eval.service import eval_orchestrator

        with Session(self.engine) as s:
            run = s.get(WorkflowEvalRun, 1)
            run.test_set_snapshot = json.dumps([
                {"id": 99, "case_key": "snap_c", "input_data": '{"q":"snap"}',
                 "expected_text": "snap_exp", "weight": 1.0, "sort_order": 0}
            ])
            s.add(run)
            s.commit()
        with patch.object(eval_orchestrator, "engine", self.engine):
            ctx = eval_orchestrator.load_eval_context(1)
        self.assertEqual([c.case_key for c in ctx["cases"]], ["snap_c"])

    def test_poll_returns_terminal(self):
        from app.modules.workflow_eval.service.eval_run_service import WorkflowEvalRunService

        with Session(self.engine) as s:
            run = s.get(WorkflowEvalRun, 1)
            run.status = EvalRunStatus.SUCCEEDED
            s.add(run)
            s.commit()
            res = WorkflowEvalRunService(s).poll(1, timeout=5, interval=1)
        self.assertEqual(res["status"], "succeeded")

    def test_poll_timeout_returns_current(self):
        from app.modules.workflow_eval.service.eval_run_service import WorkflowEvalRunService

        with Session(self.engine) as s:
            res = WorkflowEvalRunService(s).poll(1, timeout=1, interval=1)
        self.assertTrue(res.get("timeout"))
        self.assertEqual(res["status"], "pending")

    def test_sample_production_imports_golden_cases(self):
        from app.modules.workflow.model.workflow import WorkflowInstance
        from app.modules.workflow_eval.service.eval_run_service import WorkflowEvalRunService

        with Session(self.engine) as s:
            s.add(
                WorkflowInstance(
                    definition_id=1,
                    thread_id="prod1",
                    status="success",
                    state_data=json.dumps({"q": "hello", "workflow_output": {"answer": "result"}}),
                )
            )
            s.commit()
            res = WorkflowEvalRunService(s).sample_production(
                definition_id=1, test_set_id=1, limit=10, days=30
            )
            self.assertEqual(res["sampled"], 1)
            case = s.exec(
                select(WorkflowTestCase).where(
                    WorkflowTestCase.test_set_id == 1,
                    WorkflowTestCase.case_key == "prod_1",
                )
            ).first()
        self.assertIsNotNone(case)
        self.assertIn("result", case.expected_output)
        self.assertIn("production", case.tags)


if __name__ == "__main__":
    unittest.main()
