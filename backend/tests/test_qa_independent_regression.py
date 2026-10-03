"""QA 独立回归用例（严过关 / 任务 #2）。

与工程师自述相互独立：本文件只调用被测源码的公开/模块级函数，**不改动任何被测源码**；
对依赖大模型的意图分类节点走内存 monkeypatch（绝不落盘、绝不改仓库文件）。

覆盖：
- H1 深嵌套/畸形 JSON 输入不得抛异常（含远超 3000 的极端长度）
- M1 `_extract_first_json` 候选选择（含「末尾方括号引用」反例）
- M2 意图路由：精确优先 / 归一化碰撞回落 default + warning / 无子串包含 / 边界输入
- M3 f-string conversion 语义（!r/!s/!a 且 conversion 先于 format_spec）
"""

from __future__ import annotations

import asyncio
import json
import unittest

from app.modules.workflow.service import node_executors as ne
from app.modules.workflow.service.compiler import safe_eval
from app.modules.workflow.service.workflow_service import (
    _extract_first_json,
    _parse_llm_output,
    execute_intent_classifier_node,
)


class H1DeepNestingTestCase(unittest.TestCase):
    """H1：畸形深嵌套必须被兜住，返回可读内容而非抛异常。"""

    def test_recursion_error_is_real_reason(self):
        """独立验证工程师理由：json.loads('['*3000) 本身即抛 RecursionError。"""
        for n in (3000, 100000):
            with self.assertRaises(RecursionError):
                json.loads("[" * n)

    def test_extreme_inputs_do_not_raise_and_keep_raw(self):
        """远超 3000 的输入同样不抛异常，且原样保留。"""
        for raw in ("[" * 3000, "{" * 3000, "[" * 100000, "{" * 100000):
            out = _parse_llm_output(raw, "json", "o")
            self.assertEqual(out, {"o": raw}, f"未原样保留：len={len(raw)} 首字符={raw[0]}")


class M1ExtractFirstJsonTestCase(unittest.TestCase):
    """M1：候选选择策略（取解析到达位置最靠后者）。"""

    def test_intended_case_fixed(self):
        """修复目标场景：前置低置信片段不应盖过后面的真实结果。"""
        self.assertEqual(_extract_first_json('步骤 [1,2] 见下 {"a":1}'), '{"a":1}')

    def test_simple_single_fragments(self):
        self.assertEqual(_extract_first_json("见 {}\n done"), "{}")
        self.assertEqual(_extract_first_json('[{"a":1}]'), '[{"a":1}]')
        self.assertEqual(_extract_first_json("[1, 2]"), "[1, 2]")
        self.assertEqual(_extract_first_json('{"a":1}'), '{"a":1}')

    def test_trailing_bracket_reference_should_keep_object(self):
        """末尾引用不应盖过真实结果对象（第 1/2 轮已修复的行为）。"""
        self.assertEqual(_extract_first_json('答案：{"a":1} 参见 [1,2]'), '{"a":1}')
        self.assertEqual(_parse_llm_output('答案：{"a":1} 参见 [1,2]', "json", "o"), {"o": {"a": 1}})


class M2IntentClassifierTestCase(unittest.TestCase):
    """M2：意图路由匹配（不依赖真实大模型）。"""

    def _route(self, intents, default_route, model_return, query="hi"):
        # 执行器经定义模块（node_executors）全局查找 run_ai_chat，patch 必须落在定义处
        original = ne.run_ai_chat
        try:
            ne.run_ai_chat = lambda profile, prompt: model_return
            cfg = {
                "id": "ic",
                "input_variable": "",
                "intents": intents,
                "default_route": default_route,
                "model_profile_code": "p",
            }
            return asyncio.run(execute_intent_classifier_node({"query": query}, cfg))["ic_selected_route"]
        finally:
            ne.run_ai_chat = original

    def test_exact_match_preferred_over_normalized(self):
        """精确命中优先：VIP_用户 / VIP用户 不得因归一化被折叠误路由。"""
        intents = [{"name": "VIP_用户", "target_route": "A"}, {"name": "VIP用户", "target_route": "B"}]
        self.assertEqual(self._route(intents, "DEF", "VIP_用户"), "A")
        self.assertEqual(self._route(intents, "DEF", "VIP用户"), "B")

    def test_normalization_collision_falls_back_with_warning(self):
        """归一化后多候选：回落 default_route 并记 warning（不静默取首个）。"""
        intents = [{"name": "VIP_用户", "target_route": "A"}, {"name": "VIP用户", "target_route": "B"}]
        with self.assertLogs(ne.logger, level="WARNING") as cm:
            route = self._route(intents, "DEF", "VIP 用户")
        self.assertEqual(route, "DEF")
        self.assertTrue(any("歧义" in m for m in cm.output))

    def test_no_substring_containment(self):
        """绝不子串包含匹配：'咨询' 不得命中 '咨询退款'。"""
        intents = [{"name": "咨询", "target_route": "r1"}, {"name": "咨询退款", "target_route": "r2"}]
        self.assertEqual(self._route(intents, "DEF", "咨询"), "r1")
        self.assertEqual(self._route(intents, "DEF", "咨询。"), "r1")
        self.assertEqual(self._route(intents, "DEF", "**咨询退款**"), "r2")  # 归一化命中
        only_refund = [{"name": "咨询退款", "target_route": "r2"}]
        self.assertEqual(self._route(only_refund, "DEF", "咨询"), "DEF")  # 不得 r2

    def test_boundary_inputs(self):
        intents = [{"name": "咨询", "target_route": "r1"}]
        self.assertEqual(self._route(intents, "DEF", ""), "DEF")
        self.assertEqual(self._route(intents, "DEF", "。。。"), "DEF")
        self.assertEqual(self._route(intents, "DEF", "其他"), "DEF")


class M3FStringConversionTestCase(unittest.TestCase):
    """M3：safe_eval 的 f-string conversion 语义。"""

    def test_conversion_semantics(self):
        ctx = {"s": "hi", "u": "héllo", "n": 3.14159}
        self.assertEqual(safe_eval('f"{s!r}"', ctx), "'hi'")
        self.assertEqual(safe_eval('f"{s!s}"', ctx), "hi")
        self.assertEqual(safe_eval('f"{u!a}"', ctx), "'h\\xe9llo'")  # ascii() 转义非 ASCII
        self.assertEqual(safe_eval('f"{u!s}"', ctx), "héllo")
        self.assertEqual(safe_eval('f"{s}"', ctx), "hi")  # 无 conversion 维持 str
        self.assertEqual(safe_eval('f"{n:.2f}"', ctx), "3.14")

    def test_conversion_applied_before_format_spec(self):
        """conversion 先于 format_spec：先 !r 得到带引号串，再按 spec 对齐。"""
        self.assertEqual(safe_eval('f"{s!r:>6}"', {"s": "hi"}), "  'hi'")


if __name__ == "__main__":
    unittest.main()
