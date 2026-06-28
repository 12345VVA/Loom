"""LLM judge 多维 rubric 解析与评估测试（P0-1）。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.service.evaluator.base import EvalContext
from app.modules.workflow_eval.service.evaluator.llm_judge import (
    LLMJudgeEvaluator,
    _parse_judge_result,
)


class JudgeParseTestCase(unittest.TestCase):
    def test_parse_multi_dimension_json(self):
        content = '{"score": 0.8, "dimensions": {"correctness": 0.9, "clarity": 0.7}, "reason": "准确但表述略乱"}'
        r = _parse_judge_result(content)
        self.assertEqual(r["score"], 0.8)
        self.assertEqual(r["dimensions"]["correctness"], 0.9)
        self.assertIn("准确", r["reason"])

    def test_parse_score_from_dims_avg_when_no_score(self):
        r = _parse_judge_result('{"dimensions": {"a": 1.0, "b": 0.6}}')
        self.assertAlmostEqual(r["score"], 0.8)  # 无总分时取维度均值

    def test_parse_fallback_non_json(self):
        r = _parse_judge_result("总分 0.85，符合要求")
        self.assertEqual(r["score"], 0.85)  # regex fallback
        self.assertEqual(r["dimensions"], {})
        self.assertEqual(r["reason"], "")

    def test_parse_empty_returns_neutral(self):
        r = _parse_judge_result("")
        self.assertEqual(r["score"], 0.5)


class JudgeEvaluateTestCase(unittest.TestCase):
    def _ctx(self, case_config: dict) -> EvalContext:
        return EvalContext(input_data=None, expected="x", actual="y", case_config=case_config)

    def test_evaluate_dict_result_with_reason_dims(self):
        ev = LLMJudgeEvaluator()
        r = ev.evaluate(self._ctx({
            "judge_fn": lambda i, a, e: {"score": 0.9, "dimensions": {"correctness": 1.0}, "reason": "好"},
        }))
        self.assertEqual(r.score, 0.9)
        self.assertTrue(r.passed)  # 0.9 >= 0.6
        self.assertEqual(r.detail["dimensions"]["correctness"], 1.0)
        self.assertEqual(r.detail["reason"], "好")

    def test_evaluate_float_compatible(self):
        ev = LLMJudgeEvaluator()
        r = ev.evaluate(self._ctx({"judge_fn": lambda i, a, e: 0.3}))  # 旧 float 签名
        self.assertEqual(r.score, 0.3)
        self.assertFalse(r.passed)  # 0.3 < 0.6

    def test_evaluate_no_judge_fn_neutral(self):
        ev = LLMJudgeEvaluator()
        r = ev.evaluate(self._ctx({}))
        self.assertEqual(r.score, 0.5)
        self.assertFalse(r.passed)

    def test_evaluate_judge_exception_zero(self):
        ev = LLMJudgeEvaluator()

        def boom(i, a, e):
            raise RuntimeError("judge 挂了")

        r = ev.evaluate(self._ctx({"judge_fn": boom}))
        self.assertEqual(r.score, 0.0)


class SelfConsistencyTestCase(unittest.TestCase):
    def test_samples_aggregates_mean_and_std(self):
        from unittest.mock import patch

        from app.modules.workflow_eval.service.evaluator.llm_judge import build_default_judge_fn

        replies = iter([
            '{"score": 0.6, "dimensions": {"correctness": 0.6}, "reason": "r1"}',
            '{"score": 0.8, "dimensions": {"correctness": 0.8}, "reason": "r2"}',
            '{"score": 0.7, "dimensions": {"correctness": 0.7}, "reason": "r3"}',
        ])
        with patch(
            "app.modules.workflow.service.workflow_service.run_ai_chat",
            side_effect=lambda *a, **k: next(replies),
        ):
            fn = build_default_judge_fn("profile", samples=3)
            result = fn("input", "actual", "expected")
        self.assertAlmostEqual(result["score"], 0.7)  # (0.6+0.8+0.7)/3
        self.assertEqual(result["samples"], 3)
        self.assertIn("std", result)
        self.assertAlmostEqual(result["dimensions"]["correctness"], 0.7)

    def test_samples_default_one_no_aggregation(self):
        from unittest.mock import patch

        from app.modules.workflow_eval.service.evaluator.llm_judge import build_default_judge_fn

        with patch(
            "app.modules.workflow.service.workflow_service.run_ai_chat",
            return_value='{"score": 0.9, "dimensions": {"correctness": 1.0}, "reason": "ok"}',
        ) as mock_chat:
            fn = build_default_judge_fn("profile")
            result = fn("i", "a", "e")
        self.assertEqual(mock_chat.call_count, 1)  # 默认 samples=1 只调一次
        self.assertNotIn("samples", result)


if __name__ == "__main__":
    unittest.main()
