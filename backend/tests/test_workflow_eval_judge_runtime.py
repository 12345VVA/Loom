"""llm_judge 默认 judge_fn 与分数解析测试：复用 run_ai_chat（mock）。

覆盖：_parse_score 各路径、build_default_judge_fn 的 clamp/异常传播、
LLMJudgeEvaluator 注入默认 judge_fn 后产出真实分。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.modules.workflow_eval.service.evaluator import EvalContext, LLMJudgeEvaluator
from app.modules.workflow_eval.service.evaluator.llm_judge import (
    _parse_score,
    build_default_judge_fn,
)

_AI_CHAT_PATH = "app.modules.workflow.service.workflow_service.run_ai_chat"


class ParseScoreTestCase(unittest.TestCase):
    def test_json_score(self):
        self.assertAlmostEqual(_parse_score('{"score": 0.8, "reason": "ok"}'), 0.8)

    def test_bare_number(self):
        self.assertAlmostEqual(_parse_score("0.6"), 0.6)

    def test_text_with_number(self):
        self.assertAlmostEqual(_parse_score("评分：0.75"), 0.75)

    def test_invalid_fallback(self):
        self.assertEqual(_parse_score("无数字内容"), 0.5)

    def test_empty(self):
        self.assertEqual(_parse_score(""), 0.5)

    def test_above_one_clamped(self):
        # JSON 解析成功取 score，judge_fn 负责 clamp；_parse_score 本身不 clamp
        self.assertEqual(_parse_score('{"score": 1.5}'), 1.5)


class BuildJudgeFnTestCase(unittest.TestCase):
    def test_calls_run_ai_chat_and_parses(self):
        with patch(_AI_CHAT_PATH, return_value='{"score": 0.9}'):
            score = build_default_judge_fn("profile-x")({"q": "hi"}, "actual", "expected")
        self.assertEqual(score, 0.9)

    def test_clamps_above_one(self):
        with patch(_AI_CHAT_PATH, return_value='{"score": 1.5}'):
            self.assertEqual(build_default_judge_fn("p")({}, "a", "e"), 1.0)

    def test_clamps_below_zero(self):
        with patch(_AI_CHAT_PATH, return_value='{"score": -0.2}'):
            self.assertEqual(build_default_judge_fn("p")({}, "a", "e"), 0.0)

    def test_propagates_runtime_error(self):
        # 异常向上抛，交由 LLMJudgeEvaluator 兜底为 0 分
        with patch(_AI_CHAT_PATH, side_effect=RuntimeError("down")):
            with self.assertRaises(RuntimeError):
                build_default_judge_fn("p")({}, "a", "e")

    def test_custom_prompt_template_used(self):
        captured = {}

        def fake_chat(profile, prompt, system_prompt=None, response_format=None):
            captured["prompt"] = prompt
            captured["profile"] = profile
            return '{"score": 0.5}'

        with patch(_AI_CHAT_PATH, side_effect=fake_chat):
            build_default_judge_fn("p7", prompt_template="CUSTOM {input}/{actual}/{expected}")(
                "I", "A", "E"
            )
        self.assertEqual(captured["profile"], "p7")
        self.assertEqual(captured["prompt"], "CUSTOM I/A/E")


class LLMJudgeWithDefaultFnTestCase(unittest.TestCase):
    def test_evaluator_with_injected_default_fn_passes(self):
        with patch(_AI_CHAT_PATH, return_value='{"score": 0.8}'):
            ev = LLMJudgeEvaluator()
            r = ev.evaluate(
                EvalContext(
                    input_data={},
                    expected="e",
                    actual="a",
                    case_config={"judge_fn": build_default_judge_fn("p"), "threshold": 0.6},
                )
            )
        self.assertTrue(r.passed)
        self.assertEqual(r.score, 0.8)

    def test_evaluator_catches_judge_error_as_zero(self):
        def boom(*_a):
            raise RuntimeError("judge down")

        r = LLMJudgeEvaluator().evaluate(
            EvalContext(input_data={}, expected="e", actual="a", case_config={"judge_fn": boom})
        )
        self.assertFalse(r.passed)
        self.assertEqual(r.score, 0.0)


if __name__ == "__main__":
    unittest.main()
