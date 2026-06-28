"""T9b 评估器测试：注册表 + rule_match 各模式 + composite 加权 + llm_judge 注入。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.service.evaluator import (
    CompositeEvaluator,
    EvalContext,
    EvaluatorRegistry,
    LLMJudgeEvaluator,
    RuleMatchEvaluator,
)


def _ctx(actual, expected=None, **cfg) -> EvalContext:
    return EvalContext(input_data={}, expected=expected, actual=actual, case_config=cfg)


class EvaluatorRegistryTestCase(unittest.TestCase):
    def test_builtin_types_registered(self):
        types = EvaluatorRegistry.available()
        self.assertIn("rule_match", types)
        self.assertIn("composite", types)
        self.assertIn("llm_judge", types)

    def test_get_returns_instance(self):
        self.assertIsInstance(EvaluatorRegistry.get("rule_match"), RuleMatchEvaluator)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            EvaluatorRegistry.get("does_not_exist")


class RuleMatchTestCase(unittest.TestCase):
    def test_contains_default_pass(self):
        r = RuleMatchEvaluator().evaluate(_ctx("hello world", "world"))
        self.assertTrue(r.passed)
        self.assertEqual(r.score, 1.0)

    def test_contains_miss(self):
        r = RuleMatchEvaluator().evaluate(_ctx("hello", "xyz"))
        self.assertFalse(r.passed)
        self.assertEqual(r.score, 0.0)

    def test_exact_match(self):
        r = RuleMatchEvaluator().evaluate(_ctx("42", "42", mode="exact"))
        self.assertTrue(r.passed)

    def test_exact_mismatch(self):
        r = RuleMatchEvaluator().evaluate(_ctx("42", "43", mode="exact"))
        self.assertFalse(r.passed)

    def test_regex_match(self):
        r = RuleMatchEvaluator().evaluate(_ctx("error code 500", mode="regex", expected_text=r"\d{3}"))
        self.assertTrue(r.passed)

    def test_numeric_tolerance_within(self):
        r = RuleMatchEvaluator().evaluate(_ctx(3.14, 3.141, mode="numeric_tolerance", tolerance=0.01))
        self.assertTrue(r.passed)

    def test_numeric_tolerance_beyond(self):
        r = RuleMatchEvaluator().evaluate(_ctx(3.14, 4.0, mode="numeric_tolerance", tolerance=0.01))
        self.assertFalse(r.passed)


class CompositeTestCase(unittest.TestCase):
    def _children(self):
        return [
            {"type": "rule_match", "config": {"mode": "contains", "expected_text": "hello"}, "weight": 1},
            {"type": "rule_match", "config": {"mode": "contains", "expected_text": "world"}, "weight": 1},
        ]

    def test_all_pass(self):
        r = CompositeEvaluator().evaluate(_ctx("hello world", children=self._children()))
        self.assertTrue(r.passed)
        self.assertEqual(r.score, 1.0)

    def test_partial_pass_and_scores(self):
        r = CompositeEvaluator().evaluate(_ctx("hello only", children=self._children()))
        self.assertFalse(r.passed)
        self.assertEqual(r.score, 0.5)  # 一子过(1.0) 一子不过(0.0)，等权平均

    def test_empty_children_not_passed(self):
        # 空 children：无任何校验规则，不应判为通过（避免「0 分却 passed」矛盾结果污染 pass_rate/回归对比）
        r = CompositeEvaluator().evaluate(_ctx("anything", children=[]))
        self.assertFalse(r.passed)
        self.assertEqual(r.score, 0.0)


class LLMJudgeTestCase(unittest.TestCase):
    def test_injected_judge_pass(self):
        r = LLMJudgeEvaluator().evaluate(_ctx("out", judge_fn=lambda *_a: 0.8))
        self.assertTrue(r.passed)
        self.assertEqual(r.score, 0.8)

    def test_injected_judge_below_threshold(self):
        r = LLMJudgeEvaluator().evaluate(_ctx("out", judge_fn=lambda *_a: 0.3))
        self.assertFalse(r.passed)

    def test_no_judge_returns_neutral(self):
        r = LLMJudgeEvaluator().evaluate(_ctx("out"))
        self.assertEqual(r.score, 0.5)
        self.assertFalse(r.passed)

    def test_judge_exception_isolated(self):
        def boom(*_a):
            raise RuntimeError("judge down")

        r = LLMJudgeEvaluator().evaluate(_ctx("out", judge_fn=boom))
        self.assertEqual(r.score, 0.0)
        self.assertFalse(r.passed)


class RuleMatchRegexErrorTestCase(unittest.TestCase):
    def test_regex_error_recorded_in_detail(self):
        # 非法 regex（[unclosed）应记入 detail.regex_error，便于排查（不再静默）
        r = RuleMatchEvaluator().evaluate(_ctx("hello", mode="regex", expected_text="[unclosed"))
        self.assertFalse(r.passed)
        self.assertIn("regex_error", r.detail)


if __name__ == "__main__":
    unittest.main()
