"""三期 B4：_global_vars 只读注入与执行器硬编码全局读取迁移（WF-P1-1）。

语义口径：绑定输入/模板渲染/表达式求值 = node_inputs（声明优先）；
跨节点全局读取 = config["_global_vars"]（node_runner 运行时注入）。

- 直调用例：config 手动注入 _global_vars，验证「配 inputs 窄化 node_inputs 后
  仍能读到全局」+ 缺省降级 node_inputs 的兼容路径；
- 建图用例：验证 node_runner 注入点真实生效（端到端）。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_executor_context.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.node_executors import (
    _globals_from,
    execute_intent_classifier_node,
    execute_tool_executor_node,
    execute_variable_assignment_node,
    execute_variable_transform_node,
)
from app.modules.workflow.service.state import resolve_node_inputs


class GlobalsFromFallbackTestCase(unittest.TestCase):
    def test_fallback_to_variables_without_injection(self):
        """直调执行器（测试旧路径）无 _global_vars 键时降级 node_inputs，行为不变。"""
        variables = {"k": "v"}
        self.assertIs(_globals_from({}, variables), variables)
        self.assertIs(_globals_from({"other": 1}, variables), variables)

    def test_injection_wins_over_variables(self):
        """注入的 _global_vars 优先于 node_inputs。"""
        variables = {"k": "narrow"}
        globals_ = {"k": "global"}
        self.assertIs(_globals_from({"_global_vars": globals_}, variables), globals_)


class MockFallbackParametrizedTestCase(unittest.TestCase):
    """三期B4（WF-P2-1）：resolve_node_inputs mock fallback 仅单节点测试路径开启。"""

    CONFIG = {"inputs": [{"name": "query", "source": ["upstream_1", "upstream_output"]}]}

    def test_whole_graph_path_no_silent_fallback(self):
        """整图路径（默认）：上游未产出 → None 显性化，不再静默拿同名顶层变量顶替。"""
        variables = {"query": "stale_top_level"}
        node_inputs = resolve_node_inputs(variables, self.CONFIG)
        self.assertIsNone(node_inputs["query"])

    def test_standalone_path_keeps_mock_fallback(self):
        """单节点测试路径：allow_mock_fallback=True 时同名 mock 键仍顶替。"""
        variables = {"query": "mock_input"}
        node_inputs = resolve_node_inputs(variables, self.CONFIG, allow_mock_fallback=True)
        self.assertEqual(node_inputs["query"], "mock_input")

    def test_real_upstream_value_wins_over_mock(self):
        """上游真实产出优先于 mock（两种路径一致）。"""
        variables = {"upstream_1": {"query": "real"}, "query": "mock"}
        config = {"inputs": [{"name": "query", "source": ["up", "upstream_1.query"]}]}
        node_inputs = resolve_node_inputs(variables, config, allow_mock_fallback=True)
        self.assertEqual(node_inputs["query"], "real")


class LoopBatchGlobalsReadTestCase(unittest.TestCase):
    """loop/batch 的 list_variable 从 _global_vars 读取（配 inputs 后仍生效）。"""

    class _FakeBody:
        def __init__(self, fn: Callable[[dict], dict[str, Any]]):
            self._fn = fn

        async def ainvoke(self, state: dict) -> dict[str, Any]:
            return self._fn(state)

    def _loop_config(self, **overrides: Any) -> dict[str, Any]:
        config: dict[str, Any] = {
            "_compiled_body": self._FakeBody(lambda state: {"variables": state["variables"]}),
            "list_variable": "users.name_list",
            "item_variable": "loop_item",
            "output_variable": "loop_results",
        }
        config.update(overrides)
        return config

    def test_loop_reads_global_with_narrowed_inputs(self):
        """配 inputs 窄化 node_inputs 后，深层路径列表仍从 _global_vars 读到。"""
        from app.modules.workflow.service.node_executors import execute_loop_controller_node

        # node_inputs 被inputs 窄化为仅 {"x": ...}，不含列表
        variables = {"x": "narrow"}
        config = self._loop_config(
            inputs=[{"name": "x", "source": ["start_1", "x"]}],
            _global_vars={"users": {"name_list": [1, 2]}},
        )
        result = asyncio.run(execute_loop_controller_node(variables, config))
        self.assertEqual(len(result["loop_results"]), 2)

    def test_loop_fallback_reads_variables_without_injection(self):
        """缺省（无注入）降级 node_inputs——未配 inputs 时即全量变量，兼容旧行为。"""
        from app.modules.workflow.service.node_executors import execute_loop_controller_node

        result = asyncio.run(execute_loop_controller_node({"users": {"name_list": [1]}}, self._loop_config()))
        self.assertEqual(len(result["loop_results"]), 1)

    def test_batch_reads_global_with_narrowed_inputs(self):
        from app.modules.workflow.service.node_executors import execute_batch_processor_node

        config: dict[str, Any] = {
            "_compiled_body": self._FakeBody(lambda state: {"variables": state["variables"]}),
            "list_variable": "items",
            "item_variable": "batch_item",
            "output_variable": "batch_results",
            "_global_vars": {"items": [1, 2, 3]},
        }
        result = asyncio.run(execute_batch_processor_node({"x": "narrow"}, config))
        self.assertEqual(len(result["batch_results"]), 3)


class IntentGlobalsReadTestCase(unittest.TestCase):
    """intent_classifier 的 input_variable/query fallback 从 _global_vars 读取。"""

    def test_input_variable_deep_path_from_globals(self):
        config = {"id": "intent_1", "input_variable": "{ ctx.user_query }", "intents": []}
        variables = {"narrow": True}
        with patch("app.modules.workflow.service.node_executors.run_ai_chat", return_value="x"):
            result = asyncio.run(
                execute_intent_classifier_node(variables, {**config, "_global_vars": {"ctx": {"user_query": "hello"}}})
            )
        # 空 intents 走 default（None），但用例价值在：深层路径取到 query 不抛错
        self.assertIn("intent_1_selected_route", result)

    def test_query_fallback_from_globals(self):
        """未配 input_variable 时 query/user_query fallback 从 _global_vars 取。"""
        captured: dict[str, str] = {}

        def fake_chat(profile_code: str, prompt: str) -> str:
            captured["prompt"] = prompt
            return "其他"

        config = {"id": "intent_1", "intents": [{"name": "A", "description": "", "target_route": "a"}]}
        variables = {"narrow": True}
        with patch("app.modules.workflow.service.node_executors.run_ai_chat", side_effect=fake_chat):
            asyncio.run(
                execute_intent_classifier_node(variables, {**config, "_global_vars": {"user_query": "我想咨询退款"}})
            )
        self.assertIn("我想咨询退款", captured["prompt"])


class ToolExecutorGlobalsArgsTestCase(unittest.TestCase):
    """tool_executor 的 arguments 与参数值 variables. 引用从 _global_vars 读取（支持点路径）。"""

    def test_args_value_deep_path_from_globals(self):
        async def fake_weather(location: str) -> dict:
            return {"loc": location}

        config = {
            "id": "tool_1",
            "tool_code": "mock_weather_api",
            "arguments": {"location": "variables.user.city"},
            "output_variable": "tool_result",
            "_global_vars": {"user": {"city": "杭州"}},
        }
        with patch("app.modules.workflow.service.node_executors.tool_mock_weather_api", side_effect=fake_weather):
            result = asyncio.run(execute_tool_executor_node({}, config))
        self.assertEqual(result["tool_result"]["loc"], "杭州")

    def test_arguments_dict_from_globals_not_read(self):
        """复审 P1-5：globals 顶层 arguments 键不再被读取（B4 mock fallback 遗迹清除）——
        参数以 config 声明（arguments/arguments_json）为唯一来源，全局同名键不覆盖。"""

        async def fake_weather(location: str) -> dict:
            return {"loc": location}

        config = {
            "id": "tool_1",
            "tool_code": "mock_weather_api",
            "output_variable": "tool_result",
            "_global_vars": {"arguments": {"location": "北京"}},
        }
        with patch("app.modules.workflow.service.node_executors.tool_mock_weather_api", side_effect=fake_weather):
            result = asyncio.run(execute_tool_executor_node({}, config))
        # globals 的 arguments 被忽略，无 config 声明 → 空 arguments → 工具默认 location
        self.assertEqual(result["tool_result"]["loc"], "未知")


class VariableAssignmentGlobalsCtxTestCase(unittest.TestCase):
    """variable_assignment 表达式上下文：全局打底、声明覆盖、updates 最优先。"""

    def test_expression_reads_global_with_narrowed_inputs(self):
        config = {
            "id": "assign_1",
            "assignments": [{"variable_name": "out", "value_type": "expression", "value": "prefix + x"}],
            "inputs": [{"name": "x", "source": ["start_1", "x"]}],
            "_global_vars": {"prefix": "G-", "x": "STALE"},
        }
        result = asyncio.run(execute_variable_assignment_node({"x": "narrow"}, config))
        self.assertEqual(result["out"], "G-narrow")

    def test_updates_shadow_inputs(self):
        """本轮已算出的 updates 优先于 inputs/全局（前后变量依赖）。"""
        config = {
            "id": "assign_1",
            "assignments": [
                {"variable_name": "a", "value_type": "string", "value": "1"},
                {"variable_name": "b", "value_type": "expression", "value": "a + '2'"},
            ],
        }
        result = asyncio.run(execute_variable_assignment_node({}, config))
        self.assertEqual(result["b"], "12")


class VariableTransformGlobalsTestCase(unittest.TestCase):
    """variable_transform 的 input_variable 从 _global_vars 深层读取。"""

    def test_input_deep_path_from_globals(self):
        config = {
            "id": "vt_1",
            "input_variable": "{ data.tags }",
            "transform_type": "join_array",
            "transform_args": {"separator": "|"},
            "output_variable": "transformed_value",
            "_global_vars": {"data": {"tags": ["a", "b"]}},
        }
        result = asyncio.run(execute_variable_transform_node({"narrow": True}, config))
        self.assertEqual(result["transformed_value"], "a|b")

    def test_eval_expression_reads_global(self):
        config = {
            "id": "vt_1",
            "input_variable": "n",
            "transform_type": "eval_expression",
            "transform_args": {"expression": "input_value + base"},
            "output_variable": "transformed_value",
            "_global_vars": {"n": 1, "base": 10},
        }
        result = asyncio.run(execute_variable_transform_node({}, config))
        self.assertEqual(result["transformed_value"], 11)


class NodeRunnerInjectionTestCase(unittest.TestCase):
    """建图端到端：node_runner 运行时注入 _global_vars 真实生效。"""

    def test_node_runner_injects_globals(self):
        """配 inputs 窄化 node_inputs 的赋值节点，表达式仍能读到全局变量。"""
        graph_json = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "assign_1",
                    "type": "variable_assignment",
                    "config": {
                        "assignments": [
                            {"variableName": "greeting", "valueType": "expression", "value": "'hi ' + user_name"}
                        ],
                        "inputs": [{"name": "placeholder", "source": ["start_1", "placeholder"]}],
                    },
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "assign_1", "type": "direct"},
                {"source": "assign_1", "target": "end_1", "type": "direct"},
            ],
        }
        graph = WorkflowCompiler.compile_graph(graph_json).compile()
        result = asyncio.run(graph.ainvoke({"variables": {"user_name": "李白"}, "current_node": "start"}))
        self.assertEqual(result["variables"].get("greeting"), "hi 李白")


if __name__ == "__main__":
    unittest.main()
