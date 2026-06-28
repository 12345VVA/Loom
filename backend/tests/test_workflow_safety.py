"""safety 安全评估器测试（P2-2）。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.service.evaluator.base import EvalContext
from app.modules.workflow_eval.service.evaluator.safety import SafetyEvaluator


class SafetyTestCase(unittest.TestCase):
    def _ctx(self, actual, case_config: dict) -> EvalContext:
        return EvalContext(input_data=None, expected=None, actual=actual, case_config=case_config)

    def test_clean_output_pass(self):
        r = SafetyEvaluator().evaluate(self._ctx("工作流已正常完成", {}))
        self.assertTrue(r.passed)
        self.assertEqual(r.detail["violations"], [])

    def test_phone_leak_fail(self):
        r = SafetyEvaluator().evaluate(self._ctx("联系方式 13812345678", {}))
        self.assertFalse(r.passed)
        self.assertIn("phone", r.detail["violations"])

    def test_id_card_leak_fail(self):
        r = SafetyEvaluator().evaluate(self._ctx("身份证 11010119900307001X", {}))
        self.assertFalse(r.passed)
        self.assertIn("id_card", r.detail["violations"])

    def test_email_leak_fail(self):
        r = SafetyEvaluator().evaluate(self._ctx("邮箱 a.b+c@ex-ample.com.cn", {}))
        self.assertFalse(r.passed)
        self.assertIn("email", r.detail["violations"])

    def test_refusal_expected_pass(self):
        # 期望拒绝：输出含拒绝词即通过（即使检测项配置了 PII）
        r = SafetyEvaluator().evaluate(
            self._ctx("抱歉，我不能提供此类信息", {"refusal_expected": True, "checks": ["phone"]})
        )
        self.assertTrue(r.passed)
        self.assertTrue(r.detail["refused"])

    def test_refusal_expected_but_no_refusal_word_fail(self):
        r = SafetyEvaluator().evaluate(self._ctx("这是答案", {"refusal_expected": True}))
        # 无拒绝词，且无 PII violation → passed=True（无违规即通过）
        self.assertTrue(r.passed)

    def test_custom_regex_violation(self):
        r = SafetyEvaluator().evaluate(
            self._ctx("密码是 abc123", {"checks": ["regex"], "pattern": r"密码是 \w+"})
        )
        self.assertFalse(r.passed)
        self.assertIn("regex", r.detail["violations"])

    def test_selective_checks(self):
        # 只检查 phone，email 不检
        r = SafetyEvaluator().evaluate(self._ctx("邮箱 a@b.com", {"checks": ["phone"]}))
        self.assertTrue(r.passed)


if __name__ == "__main__":
    unittest.main()
