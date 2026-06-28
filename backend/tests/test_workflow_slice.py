"""数据集切片 by_tag 聚合测试（P1-2）。"""

from __future__ import annotations

import unittest

from app.modules.workflow_eval.model.enum import CaseResultStatus
from app.modules.workflow_eval.service.eval_orchestrator import _aggregate_by_tag


class _R:
    """轻量 case_result 替身（_aggregate_by_tag 只读 tags/status/score）。"""

    def __init__(self, tags, status, score=1.0):
        self.tags = tags
        self.status = status
        self.score = score


class ByTagTestCase(unittest.TestCase):
    def test_single_tag_bucket(self):
        results = [
            _R('["reasoning"]', CaseResultStatus.SUCCESS, 1.0),
            _R('["reasoning"]', CaseResultStatus.FAIL, 0.0),
            _R('["coding"]', CaseResultStatus.SUCCESS, 0.8),
        ]
        by_tag = _aggregate_by_tag(results)
        self.assertEqual(by_tag["reasoning"]["total"], 2)
        self.assertEqual(by_tag["reasoning"]["passed"], 1)
        self.assertAlmostEqual(by_tag["reasoning"]["passRate"], 0.5)
        self.assertEqual(by_tag["coding"]["total"], 1)

    def test_multi_tag_case_into_multiple_buckets(self):
        by_tag = _aggregate_by_tag([_R('["a","b"]', CaseResultStatus.SUCCESS, 1.0)])
        self.assertIn("a", by_tag)
        self.assertIn("b", by_tag)

    def test_no_tags_skipped(self):
        by_tag = _aggregate_by_tag([
            _R(None, CaseResultStatus.SUCCESS),
            _R('["x"]', CaseResultStatus.SUCCESS),
        ])
        self.assertEqual(set(by_tag.keys()), {"x"})

    def test_invalid_tags_json_skipped(self):
        self.assertEqual(_aggregate_by_tag([_R("not json", CaseResultStatus.SUCCESS)]), {})

    def test_avg_score_only_scored(self):
        # error 的 case 不计入 avgScore 分母（只 SUCCESS/FAIL 计入）
        by_tag = _aggregate_by_tag([
            _R('["x"]', CaseResultStatus.SUCCESS, 0.8),
            _R('["x"]', CaseResultStatus.FAIL, 0.4),
            _R('["x"]', CaseResultStatus.ERROR, 0.0),
        ])
        self.assertAlmostEqual(by_tag["x"]["avgScore"], 0.6)
        self.assertEqual(by_tag["x"]["total"], 3)


if __name__ == "__main__":
    unittest.main()
