"""回归对比 bootstrap 显著性测试（P0-2）。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.service.regression import _bootstrap_score_delta, _verdict


class BootstrapTestCase(unittest.TestCase):
    def test_clear_improvement_significant(self):
        sd = _bootstrap_score_delta([0.0] * 10, [1.0] * 10, n_boot=200)
        self.assertEqual(sd["delta"], 1.0)
        self.assertTrue(sd["significant"])
        self.assertTrue(sd["sufficient"])
        self.assertEqual(sd["n"], 10)

    def test_no_change_insignificant(self):
        sd = _bootstrap_score_delta([0.5] * 10, [0.5] * 10, n_boot=200)
        self.assertEqual(sd["delta"], 0.0)
        self.assertFalse(sd["significant"])

    def test_insufficient_sample(self):
        sd = _bootstrap_score_delta([0.5], [0.9], n_boot=200)
        self.assertFalse(sd["sufficient"])
        self.assertIsNone(sd["ciLow"])

    def test_empty(self):
        sd = _bootstrap_score_delta([], [], n_boot=200)
        self.assertFalse(sd["sufficient"])
        self.assertEqual(sd["n"], 0)

    def test_ci_brackets_delta(self):
        sd = _bootstrap_score_delta(
            [0.3, 0.5, 0.4, 0.6, 0.5, 0.7, 0.4, 0.5],
            [0.4, 0.5, 0.5, 0.7, 0.6, 0.7, 0.5, 0.6],
            n_boot=500,
        )
        self.assertLessEqual(sd["ciLow"], sd["delta"])
        self.assertLessEqual(sd["delta"], sd["ciHigh"])


class VerdictTestCase(unittest.TestCase):
    def test_verdict_regression(self):
        self.assertEqual(_verdict({"sufficient": True, "delta": -0.5, "significant": True}, 0.1), "regression")

    def test_verdict_improvement(self):
        self.assertEqual(_verdict({"sufficient": True, "delta": 0.5, "significant": True}, 0.1), "improvement")

    def test_verdict_insignificant_when_not_significant(self):
        self.assertEqual(_verdict({"sufficient": True, "delta": -0.5, "significant": False}, 0.1), "insignificant")

    def test_verdict_insignificant_within_threshold(self):
        # delta 在阈值内（即便显著）也算无显著变化
        self.assertEqual(_verdict({"sufficient": True, "delta": 0.05, "significant": True}, 0.1), "insignificant")

    def test_verdict_insufficient_sample(self):
        self.assertEqual(_verdict({"sufficient": False, "delta": 1.0, "significant": True}, 0.1), "insufficient_sample")


if __name__ == "__main__":
    unittest.main()
