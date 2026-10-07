"""三期 B5：状态层全量→增量——node_runner 返回 applied delta（WF-P1-3）。

核心断言：并行分支各自写不同键时互不覆盖（修复全量快照相互冲掉的问题）；
图内 state 经 reducer 累积仍是全量；output_mappings 目标键 delta 语义。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_delta_state.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.state import compute_output_delta


class ComputeOutputDeltaTestCase(unittest.TestCase):
    def test_no_mappings_returns_updates_copy(self):
        """无 mappings：executor updates 全键即增量（拷贝，不共享引用）。"""
        updates = {"a": 1}
        delta = compute_output_delta(updates, {})
        self.assertEqual(delta, {"a": 1})
        self.assertIsNot(delta, updates)

    def test_mappings_only_target_keys(self):
        """有 mappings：仅映射目标键进增量，未映射 updates 键丢弃（与全量路径一致）。"""
        delta = compute_output_delta(
            {"result": 1, "ignored": 2},
            {"result": "variables.custom_target", "other": "local_key"},
        )
        self.assertEqual(delta, {"custom_target": 1, "other": None})

    def test_none_result_safe(self):
        self.assertEqual(compute_output_delta(None, {}), {})
        # 非 variables. 前缀的 target_path 不生效（与 apply_output_mappings 既有语义一致）
        self.assertEqual(compute_output_delta(None, {"a": "b"}), {"a": None})


class ParallelBranchNoOverwriteTestCase(unittest.TestCase):
    """建图端到端：start 扇出两并行赋值节点各写不同键，汇聚后两键共存。"""

    def test_parallel_branches_both_keys_survive(self):
        graph_json = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "assign_a",
                    "type": "variable_assignment",
                    "config": {"assignments": [{"variableName": "a_out", "valueType": "string", "value": "A"}]},
                },
                {
                    "id": "assign_b",
                    "type": "variable_assignment",
                    "config": {"assignments": [{"variableName": "b_out", "valueType": "string", "value": "B"}]},
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "assign_a", "type": "direct"},
                {"source": "start_1", "target": "assign_b", "type": "direct"},
                {"source": "assign_a", "target": "end_1", "type": "direct"},
                {"source": "assign_b", "target": "end_1", "type": "direct"},
            ],
        }
        graph = WorkflowCompiler.compile_graph(graph_json).compile()
        result = asyncio.run(graph.ainvoke({"variables": {"seed": 1}, "current_node": "start"}))
        variables: dict[str, Any] = result["variables"]
        # 修复前：后合并的全量快照会冲掉先合并分支写入的键
        self.assertEqual(variables.get("a_out"), "A")
        self.assertEqual(variables.get("b_out"), "B")
        self.assertEqual(variables.get("seed"), 1)

    def test_graph_state_accumulates_full_view(self):
        """图内 state 经 reducer 累积仍是全量：串行两节点的产出同时可见。"""
        graph_json = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "assign_a",
                    "type": "variable_assignment",
                    "config": {"assignments": [{"variableName": "a_out", "valueType": "string", "value": "A"}]},
                },
                {
                    "id": "assign_b",
                    "type": "variable_assignment",
                    "config": {
                        "assignments": [{"variableName": "b_out", "valueType": "expression", "value": "a_out + '+B'"}]
                    },
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "assign_a", "type": "direct"},
                {"source": "assign_a", "target": "assign_b", "type": "direct"},
                {"source": "assign_b", "target": "end_1", "type": "direct"},
            ],
        }
        graph = WorkflowCompiler.compile_graph(graph_json).compile()
        result = asyncio.run(graph.ainvoke({"variables": {}, "current_node": "start"}))
        # b 的表达式能读到 a 的产出（图内 state 全量），且两键共存于终态
        self.assertEqual(result["variables"].get("a_out"), "A")
        self.assertEqual(result["variables"].get("b_out"), "A+B")

    def test_output_mappings_delta_via_graph(self):
        """配 outputMappings 的节点：仅目标键落进全局变量。"""
        graph_json = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "assign_a",
                    "type": "variable_assignment",
                    "config": {
                        "assignments": [
                            {"variableName": "result", "valueType": "string", "value": "R"},
                            {"variableName": "internal", "valueType": "string", "value": "I"},
                        ],
                        "outputMappings": {"result": "variables.custom_target"},
                    },
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "assign_a", "type": "direct"},
                {"source": "assign_a", "target": "end_1", "type": "direct"},
            ],
        }
        graph = WorkflowCompiler.compile_graph(graph_json).compile()
        result = asyncio.run(graph.ainvoke({"variables": {}, "current_node": "start"}))
        variables: dict[str, Any] = result["variables"]
        self.assertEqual(variables.get("custom_target"), "R")
        # 未映射键不进全局（与全量路径行为一致）
        self.assertNotIn("result", variables)
        self.assertNotIn("internal", variables)


if __name__ == "__main__":
    unittest.main()
