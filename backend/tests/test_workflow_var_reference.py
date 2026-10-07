"""变量引用链路跨栈契约测试（复审 2026-10-07 修复）。

P0-1：前端三处引导（变量下拉 refText / 语法提示 / condition 校验器）统一生成
`variables.变量名` 写法，后端求值上下文注入 variables 只读视图兼容；
P1：switch 判断变量改 _deep_get 支持点路径与列表索引；全局读取入口
（switch/transform/loop/batch/intent）统一 strip_var_prefix 归一前缀。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_var_reference.py -q
"""

from __future__ import annotations

import unittest
from typing import Any

from app.modules.workflow.service.compiler import WorkflowCompiler, _deep_get, strip_var_prefix
from app.modules.workflow.service.expressions import safe_eval
from app.modules.workflow.service.node_executors import (
    execute_loop_controller_node,
    execute_variable_transform_node,
)


class ConditionVariablesPrefixTestCase(unittest.TestCase):
    """P0-1：condition 表达式 variables. 前缀语法后端兼容。"""

    def _router(self, expression: str):
        return WorkflowCompiler.create_conditional_router(
            "cond_1", {"expression": expression, "true_route": "node_a", "false_route": "node_b"}
        )

    def test_variables_prefix_expression_routes_true(self):
        """按前端引导写 `variables.score > 80` → 正确命中 true 分支（原 NameError 必现失败）。"""
        router = self._router("variables.score > 80")
        self.assertEqual(router({"variables": {"score": 95}}), "node_a")
        self.assertEqual(router({"variables": {"score": 60}}), "node_b")

    def test_bare_name_expression_still_works(self):
        """裸名 `score > 80` 回归：两种写法共存等价。"""
        router = self._router("score > 80")
        self.assertEqual(router({"variables": {"score": 95}}), "node_a")
        self.assertEqual(router({"variables": {"score": 60}}), "node_b")

    def test_variables_prefix_nested_path(self):
        """`variables.llm_output.topic == 'A'`：前缀 + 嵌套属性访问。"""
        router = self._router("variables.llm_output.topic == 'A'")
        self.assertEqual(router({"variables": {"llm_output": {"topic": "A"}}}), "node_a")

    def test_user_variable_named_variables_equivalent(self):
        """用户变量恰好叫 variables 时，注入视图与用户键指向同一份 dict，语义等价。"""
        router = self._router("variables.flag")
        self.assertEqual(router({"variables": {"flag": True, "variables": {"flag": True}}}), "node_a")


class SwitchDeepPathTestCase(unittest.TestCase):
    """P1：switch 判断变量支持点路径 / 列表索引 / variables. 前缀。"""

    def _router(self, variable: str, cases: list[dict[str, Any]]):
        return WorkflowCompiler.create_switch_router(
            "sw_1", {"variable": variable, "cases": cases, "default_route": "node_default"}
        )

    def test_nested_dict_path(self):
        """嵌套路径（原浅层 get 恒 None → 静默走 default，已实验复现）。"""
        router = self._router("llm_output.topic", [{"value": "A", "target_route": "node_a"}])
        self.assertEqual(router({"variables": {"llm_output": {"topic": "A"}}}), "node_a")

    def test_variables_prefix_stripped(self):
        """variables. 前缀归一：与裸名写法等价。"""
        router = self._router("variables.status", [{"value": "ok", "target_route": "node_ok"}])
        self.assertEqual(router({"variables": {"status": "ok"}}), "node_ok")

    def test_list_index_path(self):
        """列表数字索引路径（与 render_template 口径一致）。"""
        router = self._router("results.0.level", [{"value": "high", "target_route": "node_high"}])
        self.assertEqual(router({"variables": {"results": [{"level": "high"}]}}), "node_high")

    def test_missing_path_falls_to_default(self):
        router = self._router("a.b.c", [{"value": "x", "target_route": "node_x"}])
        self.assertEqual(router({"variables": {"a": {}}}), "node_default")


class GlobalReadPrefixNormalizeTestCase(unittest.TestCase):
    """全局读取入口统一 strip_var_prefix：transform/loop 的输入变量接受 variables. 前缀。"""

    def test_strip_var_prefix_variants(self):
        self.assertEqual(strip_var_prefix("variables.foo"), "foo")
        self.assertEqual(strip_var_prefix("{variables.foo}"), "foo")
        self.assertEqual(strip_var_prefix("foo"), "foo")
        self.assertEqual(strip_var_prefix(""), "")

    def test_transform_input_variable_with_prefix(self):
        """variable_transform 输入变量填 `variables.tags`（复制自变量引用文案）→ 仍能读取全局。"""
        import asyncio

        result = asyncio.run(
            execute_variable_transform_node(
                {"tags": ["a", "b"]},
                {"input_variable": "variables.tags", "transform_type": "join_array", "transform_args": {}},
            )
        )
        self.assertEqual(result, {"transformed_value": "a,b"})

    def test_loop_list_variable_with_prefix(self):
        """loop 列表变量填 `variables.items` → 仍能读取全局列表。"""

        class _StubBody:
            async def ainvoke(self, state: dict) -> dict:
                return state

        import asyncio

        result = asyncio.run(
            execute_loop_controller_node(
                {"items": ["a"]},
                {"_compiled_body": _StubBody(), "list_variable": "variables.items"},
            )
        )
        self.assertEqual(len(result["loop_results"]), 1)

    def test_deep_get_list_index(self):
        self.assertEqual(_deep_get({"a": [{"b": 1}]}, "a.0.b"), 1)
        self.assertIsNone(_deep_get({"a": [{"b": 1}]}, "a.5.b"))
        self.assertIsNone(_deep_get({"a": [{"b": 1}]}, "a.x.b"))


class EvalContextVariablesViewTestCase(unittest.TestCase):
    """safe_eval 层面：注入的 variables 视图支持属性与下标访问。"""

    def test_attribute_and_subscript_access(self):
        ctx = {"score": 95, "variables": {"score": 95}}
        self.assertTrue(safe_eval("variables.score > 80", ctx))
        self.assertTrue(safe_eval("variables['score'] > 80", ctx))


if __name__ == "__main__":
    unittest.main()
