"""三期 B7（WF-P2-10）：deprecated `tool` 节点下架与存量图自动迁移。

- migrate_legacy_tool_nodes：config 映射 / mock_data 丢弃 / 非 tool 不动 / 原地修改；
- 加载入口迁移后可正常编译执行；绕过加载入口的由 validate_graph 拒绝；
- tool 执行器不再注册。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_tool_migration.py -q
"""

from __future__ import annotations

import unittest

from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.graph_validate import migrate_legacy_tool_nodes, validate_graph
from app.modules.workflow.service.state import node_registry


class MigrateLegacyToolNodesTestCase(unittest.TestCase):
    def test_tool_node_migrated_with_config_mapping(self):
        graph = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {
                    "id": "t1",
                    "type": "tool",
                    "name": "OldTool",
                    "config": {"tool_name": "my_tool", "output_variable": "custom_out"},
                },
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "t1", "type": "direct"},
                {"source": "t1", "target": "end_1", "type": "direct"},
            ],
        }
        result = migrate_legacy_tool_nodes(graph)
        node = result["nodes"][1]
        self.assertEqual(node["type"], "tool_executor")
        self.assertEqual(node["config"], {"toolCode": "my_tool", "outputVariable": "custom_out"})

    def test_mock_data_dropped_and_missing_fields_tolerated(self):
        graph = {
            "nodes": [{"id": "t1", "type": "tool", "name": "T", "config": {"tool_name": "x", "mock_data": {"a": 1}}}],
            "edges": [],
        }
        node = migrate_legacy_tool_nodes(graph)["nodes"][0]
        self.assertEqual(node["config"], {"toolCode": "x"})  # mock_data 丢弃、output 落默认

    def test_non_tool_nodes_untouched(self):
        graph = {"nodes": [{"id": "te", "type": "tool_executor", "config": {"toolCode": "k"}}], "edges": []}
        result = migrate_legacy_tool_nodes(graph)
        self.assertEqual(result["nodes"][0]["config"], {"toolCode": "k"})

    def test_migrated_graph_compiles(self):
        """存量 tool 图经迁移后可正常编译（执行入口统一迁移的端到端语义）。"""
        graph = migrate_legacy_tool_nodes(
            {
                "nodes": [
                    {"id": "start_1", "type": "start", "config": {}},
                    {"id": "t1", "type": "tool", "name": "OldTool", "config": {"tool_name": "my_tool"}},
                    {"id": "end_1", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start_1", "target": "t1", "type": "direct"},
                    {"source": "t1", "target": "end_1", "type": "direct"},
                ],
            }
        )
        builder = WorkflowCompiler.compile_graph(graph)
        self.assertIn("t1", builder.nodes)

    def test_validate_graph_rejects_bypassing_tool(self):
        """绕过加载入口直造 graph_json 的 tool 节点被 validate_graph 显式拒绝。"""
        graph = {
            "nodes": [
                {"id": "start_1", "type": "start", "config": {}},
                {"id": "t1", "type": "tool", "name": "OldTool", "config": {}},
                {"id": "end_1", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start_1", "target": "t1", "type": "direct"},
                {"source": "t1", "target": "end_1", "type": "direct"},
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("tool_executor", str(cm.exception))

    def test_tool_executor_no_longer_registered(self):
        """tool 执行器已下架（不再注册）；tool_executor 仍在。"""
        self.assertIsNone(node_registry.get("tool"))
        self.assertIsNotNone(node_registry.get("tool_executor"))


if __name__ == "__main__":
    unittest.main()
