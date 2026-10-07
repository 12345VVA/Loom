"""三期 B6：validate_graph config schema 校验、条件路由检查与 D3 fail-fast。

- schema 必填/类型（WF-P2-5）：condition expression、switch variable/cases、
  loop listVariable、batch batchListVariable；存量 snake 配置双风格匹配；
- 条件类节点至少一条非 END 路由（WF-P2-12）：无路由边且无 config 显式路由 → 拒绝；
- D3（已决 fail-fast）：condition 求值失败默认节点失败，onExpressionError="fallback"
  显式回落；intent 空 intents 不再强制 model。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_validation.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.modules.workflow.service.compiler import NodeExecutionError, WorkflowCompiler
from app.modules.workflow.service.graph_validate import validate_graph


def _base_graph(**extra_nodes: dict[str, Any]) -> dict[str, Any]:
    """合法最小图：start → 各附加节点 → end。附加节点按其自身 id 连边。"""
    nodes: list[dict[str, Any]] = [{"id": "start_1", "type": "start", "config": {}}]
    edges: list[dict[str, Any]] = []
    for node in extra_nodes.values():
        nodes.append(node)
        edges.append({"source": "start_1", "target": node["id"], "type": "direct"})
    nodes.append({"id": "end_1", "type": "end", "config": {}})
    return {"nodes": nodes, "edges": edges}


def _chain(graph: dict[str, Any], source: str, target: str, handle: str | None = None) -> None:
    edge: dict[str, Any] = {"source": source, "target": target, "type": "direct"}
    if handle:
        edge["sourceHandle"] = handle
    graph["edges"].append(edge)


class SchemaValidationTestCase(unittest.TestCase):
    def test_condition_empty_expression_rejected(self):
        graph = _base_graph(cond={"id": "c1", "type": "condition", "name": "C", "config": {"expression": ""}})
        _chain(graph, "c1", "end_1", "true")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("条件表达式", str(cm.exception))

    def test_condition_missing_config_rejected(self):
        """复审 P1-2：condition 完全无 config（仅有 handle 边）不再绕过必填校验——
        此前 `if not config: continue` 放行，编译期 expression 缺失回落恒真兜底。"""
        graph = _base_graph(cond={"id": "c1", "type": "condition", "name": "C"})
        _chain(graph, "c1", "end_1", "true")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("条件表达式", str(cm.exception))

    def test_no_schema_type_with_empty_config_passes(self):
        """无 schema 声明的节点类型（如 variable_assignment）空 config 不受影响。"""
        graph = _base_graph(va={"id": "v1", "type": "variable_assignment", "name": "V", "config": {}})
        validate_graph(graph)

    def test_condition_valid_expression_passes(self):
        graph = _base_graph(cond={"id": "c1", "type": "condition", "name": "C", "config": {"expression": "1 > 0"}})
        _chain(graph, "c1", "end_1", "true")
        validate_graph(graph)

    def test_switch_missing_variable_rejected(self):
        graph = _base_graph(sw={"id": "s1", "type": "switch", "name": "S", "config": {"variable": "", "cases": []}})
        _chain(graph, "s1", "end_1", "case_1")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("分支变量", str(cm.exception))

    def test_switch_missing_cases_rejected(self):
        graph = _base_graph(sw={"id": "s1", "type": "switch", "name": "S", "config": {"variable": "x", "cases": []}})
        _chain(graph, "s1", "end_1", "case_1")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("cases", str(cm.exception))

    def test_loop_snake_case_config_matched(self):
        """存量 variable_transform 风格的 snake 配置（list_variable）双风格匹配通过。"""
        graph = _base_graph(
            loop={
                "id": "l1",
                "type": "loop_controller",
                "name": "L",
                "config": {"list_variable": "items", "bodyGroupId": "g1"},
            },
            g1={"id": "g1", "type": "loop_body_group", "config": {"controllerNodeId": "l1"}},
            body={"id": "b1", "type": "variable_assignment", "config": {}, "parentNode": "g1"},
        )
        _chain(graph, "l1", "end_1")
        validate_graph(graph)

    def test_loop_missing_list_variable_rejected(self):
        """已配体路由但缺 listVariable → schema 层拦截（体路由校验先行通过）。"""
        graph = _base_graph(
            loop={
                "id": "l1",
                "type": "loop_controller",
                "name": "L",
                "config": {"listVariable": "  ", "bodyGroupId": "g1"},
            },
            g1={"id": "g1", "type": "loop_body_group", "config": {"controllerNodeId": "l1"}},
            body={"id": "b1", "type": "variable_assignment", "config": {}, "parentNode": "g1"},
        )
        _chain(graph, "l1", "end_1")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("循环列表变量", str(cm.exception))

    def test_batch_missing_batch_list_variable_rejected(self):
        graph = _base_graph(
            batch={
                "id": "b1",
                "type": "batch_processor",
                "name": "B",
                "config": {"bodyGroupId": "g1"},
            },
            g1={"id": "g1", "type": "loop_body_group", "config": {"controllerNodeId": "b1"}},
            body={"id": "n1", "type": "variable_assignment", "config": {}, "parentNode": "g1"},
        )
        _chain(graph, "b1", "end_1")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("批处理列表变量", str(cm.exception))


class ConditionalRouteValidationTestCase(unittest.TestCase):
    def test_condition_without_route_edges_rejected(self):
        """condition 仅有无句柄普通出边（无 true/false）且无 config 路由 → 拒绝。"""
        graph = _base_graph(cond={"id": "c1", "type": "condition", "name": "C", "config": {"expression": "True"}})
        _chain(graph, "c1", "end_1")  # 无 sourceHandle，推导不出路由
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("没有任何可解析的路由", str(cm.exception))

    def test_condition_with_handle_edge_passes(self):
        graph = _base_graph(cond={"id": "c1", "type": "condition", "name": "C", "config": {"expression": "True"}})
        _chain(graph, "c1", "end_1", "true")
        validate_graph(graph)

    def test_intent_without_routes_rejected(self):
        """intent 无 intent_*/default 句柄出边、无 defaultRoute → 拒绝。"""
        graph = _base_graph(
            it={
                "id": "i1",
                "type": "intent_classifier",
                "name": "I",
                "config": {
                    "modelProfileCode": "p1",
                    "intents": [{"id": "x", "name": "A", "description": ""}],
                },
            }
        )
        _chain(graph, "i1", "end_1")  # 普通边，非 intent_x 句柄
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("没有任何可解析的路由", str(cm.exception))

    def test_intent_config_default_route_passes(self):
        """历史图 config.defaultRoute 显式兜底 → 视为有路由。"""
        graph = _base_graph(
            it={
                "id": "i1",
                "type": "intent_classifier",
                "name": "I",
                "config": {
                    "modelProfileCode": "p1",
                    "intents": [{"id": "x", "name": "A", "description": ""}],
                    "defaultRoute": "end_1",
                },
            }
        )
        _chain(graph, "i1", "end_1")
        validate_graph(graph)

    def test_intent_empty_intents_no_model_required(self):
        """空 intents 不再强制 model（执行器直落 default_route，不经过 LLM）。"""
        graph = _base_graph(it={"id": "i1", "type": "intent_classifier", "name": "I", "config": {"intents": []}})
        _chain(graph, "i1", "end_1", "default")
        validate_graph(graph)

    def test_intent_with_intents_still_requires_model(self):
        graph = _base_graph(
            it={
                "id": "i1",
                "type": "intent_classifier",
                "name": "I",
                "config": {"intents": [{"id": "x", "name": "A", "description": ""}]},
            }
        )
        _chain(graph, "i1", "end_1", "intent_x")
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("模型 Profile", str(cm.exception))


class D3ExpressionErrorTestCase(unittest.TestCase):
    """condition 求值失败语义：默认 fail-fast，onExpressionError="fallback" 显式回落。"""

    def _graph(self, expression: str, extra_config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "c1",
                    "type": "condition",
                    "name": "C",
                    "config": {"expression": expression, **(extra_config or {})},
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "c1", "type": "direct"},
                {"source": "c1", "target": "end_1", "type": "direct", "sourceHandle": "true"},
            ],
        }

    def test_fail_fast_by_default(self):
        """求值失败（未定义变量）默认抛 NodeExecutionError（node_id 归因，attempts=0）。"""
        compiled = WorkflowCompiler.compile_graph(self._graph("undefined_name > 1")).compile()
        with self.assertRaises(NodeExecutionError) as cm:
            asyncio.run(compiled.ainvoke({"variables": {}, "current_node": "start"}))
        self.assertEqual(cm.exception.node_id, "c1")
        self.assertEqual(cm.exception.attempts, 0)

    def test_fallback_explicit_config(self):
        """onExpressionError="fallback" 显式配置时回落 false 路由（END），执行正常收尾。"""
        graph = self._graph("undefined_name > 1", {"onExpressionError": "fallback"})
        compiled = WorkflowCompiler.compile_graph(graph).compile()
        result = asyncio.run(compiled.ainvoke({"variables": {}, "current_node": "start"}))
        self.assertEqual(result["current_node"], "end_1")


if __name__ == "__main__":
    unittest.main()
