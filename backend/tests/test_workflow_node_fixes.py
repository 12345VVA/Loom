"""节点模块六项缺陷修复的回归锁定用例（H1 / M1 / M2 / M3）。

这些用例在修复前为红、修复后为绿，用于把已确认的缺陷钉死，防止后续重构回退。
H2（前端启发式字段名）与 H3（依赖下限）不在此文件覆盖：
    - H2 由 `frontend` 的 `npm run type-check` + 源码锚点校验覆盖；
    - H3 由 `scripts/verify_node_audit_20260922.py` 的 [G] 源码锚点覆盖。

在 backend/ 目录下用 venv 解释器运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_node_fixes.py -q
"""

from __future__ import annotations

import asyncio
import unittest

import app.modules.workflow.service.workflow_service as ws  # noqa: F401  触发执行器注册
from app.modules.workflow.service.compiler import safe_eval

_LOGGER_NAME = "app.modules.workflow.service.workflow_service"


class H1RecursionDegradeTestCase(unittest.TestCase):
    """H1：畸形深嵌套 JSON 触发 RecursionError 时，必须降级为保留原文而非抛出。"""

    def test_deep_nested_array_degrades_to_raw_text(self) -> None:
        raw = "[" * 3000
        result = ws._parse_llm_output(raw, "json", "o")
        self.assertEqual(result, {"o": raw})

    def test_deep_nested_in_code_block_degrades(self) -> None:
        # 代码块路径同样不得击穿：Tier2 候选解析失败后仍应回落原文
        raw = "```json\n" + "[" * 3000 + "\n```"
        result = ws._parse_llm_output(raw, "json", "o")
        self.assertEqual(result, {"o": raw})

    def test_pathological_input_is_bounded(self) -> None:
        """H1 性能防护：连续方括号病态输入不得长时间占住 worker，应快速返回 None。

        修复前该路径对每个位置都 raw_decode、每次递归到上限才抛，'['*100000 需数十秒；
        加尝试上限后应稳定在毫秒级（此断言用 2s 宽限，只防防护被移除导致的量级回归）。
        """
        import time

        for n in (3000, 100000):
            with self.subTest(n=n):
                raw = "[" * n
                start = time.perf_counter()
                result = ws._extract_first_json(raw)
                elapsed = time.perf_counter() - start
                self.assertIsNone(result)
                self.assertLess(elapsed, 2.0, f"n={n} 耗时 {elapsed:.2f}s，性能防护可能被移除")


class M1ExtractCandidateTestCase(unittest.TestCase):
    """M1：候选选择须对象优先、同类取最长，并剔除被包含的内层片段。"""

    def test_prefers_trailing_object_over_leading_number_array(self) -> None:
        self.assertEqual(ws._extract_first_json('步骤 [1,2] 见下 {"a":1}'), '{"a":1}')

    def test_bidirectional_bracket_references(self) -> None:
        """双向反例：正文「前」或「后」多出方括号，都应取回真正的对象结果。"""
        cases = [
            ('答案：{"a":1} 参见 [1,2]', '{"a":1}'),  # 后置引用（第 2 轮修复）
            ('{"a":1} 参考文献 [1,2]', '{"a":1}'),  # 后置引用
            ('结果 {"answer": 42} 依据 [1,2,3]', '{"answer": 42}'),  # 后置引用
            ('前缀 {"a":1} 后置 {}', '{"a":1}'),  # 后置空对象，取更完整者
            ('步骤 [1,2] 见下 {"a":1}', '{"a":1}'),  # 前置引用（第 1 轮修复）
            ('提示 [1,2,3,4] 结果 {"a":1}', '{"a":1}'),  # 前置引用
            ('详见 [文档](http://x) 结果 {"a":1}', '{"a":1}'),  # 前置中括号 + markdown 链接
            ("见 {}\n done", "{}"),
            ('[{"a":1}]', '[{"a":1}]'),  # 外层优先
            ("[1, 2]", "[1, 2]"),
            ("正文 [1] 结束", "[1]"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(ws._extract_first_json(src), expected)

    def test_high_position_count_does_not_cause_fail_open(self) -> None:
        """尝试上限是数量级防护，不得在结果之前的位置洪泛时提前截断（fail-open）。

        第 2 轮曾用 _MAX_JSON_CANDIDATE_ATTEMPTS=200 纯位置计数，导致
        `"[0] " * 200 + '{"a":1}'` 在到达真实结果前即被截断、回落到 `[0]`（误判）。
        第 3 轮改为「高尝试上限 + 深嵌套失败预算」，正常结果应被完整找回。
        """
        cases = [
            ("[0] " * 199 + '{"a":1}', '{"a":1}'),
            ("[0] " * 200 + '{"a":1}', '{"a":1}'),
            ("[0] " * 300 + '{"a":1}', '{"a":1}'),
            ("{} " * 300 + '{"a":1}', '{"a":1}'),
        ]
        for src, expected in cases:
            with self.subTest(n_positions=src.count("[") + src.count("{")):
                self.assertEqual(ws._extract_first_json(src), expected)

    def test_scan_truncation_falls_back_safe(self) -> None:
        """扫描确被截断（超尝试上限 / 深嵌套失败预算耗尽）时须回落 None（fail-safe），
        绝不返回截断点之前的残缺片段（否则会把正文里的 `[0]` 当结果）。"""
        # 位置数超过尝试上限：结果位于截断点之后 → 回落原文
        over = "[0] " * (ws._MAX_JSON_CANDIDATE_ATTEMPTS + 1) + '{"a":1}'
        self.assertIsNone(ws._extract_first_json(over))
        # 深嵌套失败预算耗尽（recursion_failures 达 _MAX_JSON_RECURSION_FAILURES）→ 回落原文
        self.assertIsNone(ws._extract_first_json("[" * 3000))

    def test_candidate_flood_is_not_quadratic(self) -> None:
        """成功候选洪泛须近线性处理，不得出现「包含判断」O(n²) 的秒级回归。

        第 3 轮曾把尝试上限提到 10000 却保留 O(n²) 两两比对，导致 `'[0] '*10000` 约 9 秒；
        改为「排序 + 单遍 max_end 扫描」后应为毫秒级。此断言用 1s 宽限，只防 O(n²) 回归。
        """
        import time

        for src, expected in (("[0] " * 10000, "[0]"), ("[1,2,3,4,5] " * 10000, "[1,2,3,4,5]")):
            with self.subTest(pattern=repr(src[:14])):
                start = time.perf_counter()
                result = ws._extract_first_json(src)
                elapsed = time.perf_counter() - start
                self.assertEqual(result, expected)
                self.assertLess(elapsed, 1.0, f"候选洪泛耗时 {elapsed:.3f}s，疑似 O(n²) 回归")

    def test_known_ambiguity_array_result_vs_object_priority(self) -> None:
        """已知取舍（对象/数组混合场景的固有歧义）—— 固化决策，非回归。

        当结果本身是**数组**、而正文另含**对象**片段时，「对象优先」必然取对象。
        按类型选（对象优先）或按长度选都会在另一方向出错，属固有歧义；团队决定保留
        「对象优先」、不做进一步区分（详见任务报告）。本用例把该决策显式固化下来，
        防止后续被无意变更 —— 若要做 isEmpty 分层等改进，须同步更新此用例。
        """
        self.assertEqual(ws._extract_first_json('输出 [{"id":1}] 说明 {}'), "{}")
        self.assertEqual(ws._extract_first_json('[1, 2] 说明 {"note": "x"}'), '{"note": "x"}')

    def test_single_empty_object_still_returned(self) -> None:
        self.assertEqual(ws._extract_first_json("见 {}\n done"), "{}")

    def test_outer_container_preferred_over_inner(self) -> None:
        self.assertEqual(ws._extract_first_json('[{"a":1}]'), '[{"a":1}]')

    def test_no_json_returns_none(self) -> None:
        self.assertIsNone(ws._extract_first_json("这里没有任何 JSON"))

    def test_existing_behaviors_not_regressed(self) -> None:
        cases = [
            ('{"a":1}', {"a": 1}),
            ('```json\n{"a":1}\n```', {"a": 1}),
            ('好的，输出如下：\n```json\n{"a":1}\n```', {"a": 1}),
            ('解析结果：{"data": 1}', {"data": 1}),
            ("[1, 2]", [1, 2]),
        ]
        for content, expected in cases:
            with self.subTest(content=content):
                self.assertEqual(ws._parse_llm_output(content, "json", "out"), {"out": expected})

    def test_non_json_still_degrades_to_raw_text(self) -> None:
        text = "完全不是 JSON 的一段话"
        self.assertEqual(ws._parse_llm_output(text, "json", "out"), {"out": text})

    def test_text_mode_never_parses(self) -> None:
        self.assertEqual(ws._parse_llm_output('{"data": 1}', "text", "out"), {"out": '{"data": 1}'})


class M2IntentRoutingTestCase(unittest.TestCase):
    """M2：意图路由须先精确匹配，归一化碰撞多命中时回落 default 而非静默取首个。"""

    @staticmethod
    def _route(matched: str, intents: list[dict], default: str = "default") -> str:
        original = ws.run_ai_chat
        ws.run_ai_chat = lambda *a, **k: matched  # type: ignore[assignment]
        try:
            config = {
                "id": "ic",
                "intents": intents,
                "default_route": default,
                "model_profile_code": "m",
            }
            result = asyncio.run(ws.execute_intent_classifier_node({}, config))
        finally:
            ws.run_ai_chat = original  # type: ignore[assignment]
        return result["ic_selected_route"]

    _COLLIDING = [
        {"name": "VIP_用户", "target_route": "r_underscore"},
        {"name": "VIP用户", "target_route": "r_plain"},
    ]

    def test_exact_match_underscore(self) -> None:
        self.assertEqual(self._route("VIP_用户", self._COLLIDING), "r_underscore")

    def test_exact_match_plain(self) -> None:
        # 修复前：两者归一化后相等，循环取首个 → 会误路由到 r_underscore
        self.assertEqual(self._route("VIP用户", self._COLLIDING), "r_plain")

    def test_normalization_collision_falls_back_with_warning(self) -> None:
        # "**VIP用户**" 精确匹配落空，归一化（去 markdown 强调符）后同时命中两个意图 → 歧义
        with self.assertLogs(_LOGGER_NAME, level="WARNING") as captured:
            route = self._route("**VIP用户**", self._COLLIDING)
        self.assertEqual(route, "default")
        self.assertTrue(any("歧义" in line for line in captured.output))

    def test_no_substring_match(self) -> None:
        intents = [
            {"name": "咨询", "target_route": "r1"},
            {"name": "咨询退款", "target_route": "r2"},
        ]
        self.assertEqual(self._route("咨询", intents), "r1")

    def test_decorated_label_single_normalized_hit(self) -> None:
        intents = [{"name": "咨询", "target_route": "r1"}]
        self.assertEqual(self._route("(咨询)", intents), "r1")

    def test_unmatched_falls_back(self) -> None:
        intents = [{"name": "咨询", "target_route": "r1"}]
        self.assertEqual(self._route("别的", intents), "default")


class M3FstringConversionTestCase(unittest.TestCase):
    """M3：f-string 的 conversion（!r/!s/!a）须生效，且先于 format_spec。"""

    def test_repr(self) -> None:
        self.assertEqual(safe_eval('f"{s!r}"', {"s": "hi"}), "'hi'")

    def test_str(self) -> None:
        self.assertEqual(safe_eval('f"{s!s}"', {"s": "hi"}), "hi")

    def test_ascii(self) -> None:
        self.assertEqual(safe_eval('f"{s!a}"', {"s": "héllo"}), "'h\\xe9llo'")

    def test_no_conversion_unchanged(self) -> None:
        self.assertEqual(safe_eval('f"{s}"', {"s": "hi"}), "hi")

    def test_conversion_applied_before_format_spec(self) -> None:
        self.assertEqual(safe_eval('f"{s!r:>6}"', {"s": "hi"}), "  'hi'")


if __name__ == "__main__":
    unittest.main()
