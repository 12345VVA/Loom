"""JSON 结构校验评估器测试（P0-5）。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.service.evaluator.base import EvalContext
from app.modules.workflow_eval.service.evaluator.json_schema import JsonSchemaEvaluator


class JsonSchemaTestCase(unittest.TestCase):
    def _ctx(self, actual, case_config: dict, expected=None) -> EvalContext:
        return EvalContext(input_data=None, expected=expected, actual=actual, case_config=case_config)

    def test_keys_all_hit_pass(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx('{"a":1,"b":2,"c":3}', {"expected_keys": ["a", "b"]}))
        self.assertTrue(r.passed)
        self.assertEqual(r.score, 1.0)

    def test_keys_partial_score(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx('{"a":1}', {"expected_keys": ["a", "b", "c"]}))
        self.assertFalse(r.passed)
        self.assertAlmostEqual(r.score, 1 / 3, places=3)
        self.assertEqual(r.detail["missing"], ["b", "c"])

    def test_exact_keys_match(self):
        r = JsonSchemaEvaluator().evaluate(
            self._ctx('{"a":1,"b":2}', {"mode": "exact_keys", "expected_keys": ["a", "b"]})
        )
        self.assertTrue(r.passed)

    def test_exact_keys_extra_fail(self):
        r = JsonSchemaEvaluator().evaluate(
            self._ctx('{"a":1,"b":2,"c":3}', {"mode": "exact_keys", "expected_keys": ["a", "b"]})
        )
        self.assertFalse(r.passed)

    def test_invalid_json_zero(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx("not json", {"expected_keys": ["a"]}))
        self.assertEqual(r.score, 0.0)
        self.assertFalse(r.passed)

    def test_not_object_zero(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx("[1,2,3]", {"expected_keys": ["a"]}))
        self.assertEqual(r.score, 0.0)
        self.assertIn("不是 JSON 对象", r.detail["error"])

    def test_expected_keys_from_ctx(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx('{"a":1,"b":2}', {}, expected=["a", "b"]))
        self.assertTrue(r.passed)  # expected_keys 缺省取 ctx.expected

    def test_no_expected_keys_skip(self):
        r = JsonSchemaEvaluator().evaluate(self._ctx('{"a":1}', {}))
        self.assertTrue(r.passed)  # 无 expected_keys 跳过校验


if __name__ == "__main__":
    unittest.main()
