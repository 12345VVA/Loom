"""工作流 compiler 直接单测：validate_graph / compile_graph / NodeExecutorRegistry / 常量。

参考 test_workflow_retry.py 的 unittest 风格，不依赖数据库（compiler 是纯函数）。
compile_graph 内部会延迟 import workflow_service 完成执行器注册，无需额外 mock。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.modules.workflow.service import compiler as compiler_mod
from app.modules.workflow.service.compiler import (
    CONDITIONAL_NODE_TYPES,
    NodeExecutionError,
    NodeExecutorRegistry,
    SUBGRAPH_NODE_TYPES,
    UNTESTABLE_NODE_TYPES,
    WorkflowCompiler,
    node_registry,
    validate_graph,
)


# --- 测试图构造 helper ---


def _start_node(node_id: str = "start_1") -> dict:
    return {"id": node_id, "type": "start", "name": "Start"}


def _end_node(node_id: str = "end_1") -> dict:
    return {"id": node_id, "type": "end", "name": "End"}


def _llm_node(node_id: str, profile_code: str = "p1") -> dict:
    return {
        "id": node_id,
        "type": "llm",
        "name": f"LLM-{node_id}",
        "config": {"modelProfileCode": profile_code},
    }


def _edge(src: str, tgt: str, eid: str | None = None) -> dict:
    return {"id": eid or f"e_{src}_{tgt}", "source": src, "target": tgt}


def _simple_graph() -> dict:
    """start → llm → end 合法图。"""
    return {
        "nodes": [_start_node(), _llm_node("llm_1"), _end_node()],
        "edges": [_edge("start_1", "llm_1"), _edge("llm_1", "end_1")],
    }


class ValidateGraphTestCase(unittest.TestCase):
    """validate_graph 拓扑结构校验测试。"""

    def test_valid_simple_graph_passes(self):
        """合法的 start → llm → end 图通过校验，不抛异常。"""
        validate_graph(_simple_graph())

    def test_cycle_raises(self):
        """两个非条件节点形成环，校验报错（含'环'/'cycle'关键字）。"""
        graph = {
            "nodes": [
                _start_node(),
                _llm_node("a"),
                _llm_node("b"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "a"),
                _edge("a", "b"),
                _edge("b", "a"),  # 形成环 a ↔ b
                _edge("a", "end_1"),
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        msg = str(cm.exception)
        self.assertTrue(
            "环" in msg or "cycle" in msg.lower(),
            f"错误信息应提及环/cycle: {msg}",
        )

    def test_missing_start_raises(self):
        """图中无 start 节点，校验报错。"""
        graph = {
            "nodes": [_llm_node("llm_1"), _end_node()],
            "edges": [_edge("llm_1", "end_1")],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("start", str(cm.exception))

    def test_multiple_start_raises(self):
        """多个 start 节点，校验报错。"""
        graph = {
            "nodes": [
                _start_node("start_1"),
                _start_node("start_2"),
                _llm_node("llm_1"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "llm_1"),
                _edge("start_2", "llm_1"),
                _edge("llm_1", "end_1"),
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("start", str(cm.exception))

    def test_missing_node_id_raises(self):
        """节点缺 id 字段，校验报错。"""
        graph = {
            "nodes": [
                {"type": "start"},  # 缺 id
                _llm_node("llm_1"),
                _end_node(),
            ],
            "edges": [],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("id", str(cm.exception))

    def test_missing_node_type_raises(self):
        """节点缺 type 字段，校验报错。"""
        graph = {
            "nodes": [
                {"id": "start_1"},  # 缺 type
                _llm_node("llm_1"),
                _end_node(),
            ],
            "edges": [],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("type", str(cm.exception))

    def test_start_without_outgoing_edge_raises(self):
        """start 节点无出边，校验报错（langgraph 编译会报 entrypoint 缺失）。"""
        graph = {
            "nodes": [_start_node(), _llm_node("llm_1"), _end_node()],
            "edges": [_edge("llm_1", "end_1")],  # start_1 无出边
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("start", str(cm.exception).lower())

    def test_dangling_edge_source_raises(self):
        """连线引用不存在的源节点，校验报错。"""
        graph = {
            "nodes": [_start_node(), _end_node()],
            "edges": [_edge("start_1", "ghost")],  # ghost 不存在
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("ghost", str(cm.exception))

    def test_dangling_edge_target_raises(self):
        """连线引用不存在的目标节点，校验报错。

        需先让 start 有合法出边，通过 start 出边校验后才能到达悬空边校验。
        """
        graph = {
            "nodes": [_start_node(), _end_node()],
            "edges": [
                _edge("start_1", "end_1"),  # 合法边，让 start 通过出边校验
                _edge("start_1", "ghost"),  # ghost 不存在（dangling target）
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("ghost", str(cm.exception))

    def test_duplicate_edge_raises(self):
        """重复连线（同 source/target）校验报错。"""
        graph = {
            "nodes": [_start_node(), _llm_node("llm_1"), _end_node()],
            "edges": [
                _edge("start_1", "llm_1", "e1"),
                _edge("start_1", "llm_1", "e2"),  # 重复
                _edge("llm_1", "end_1"),
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("重复", str(cm.exception))

    def test_isolated_node_raises(self):
        """孤立工作节点（无任何连线），校验报错。"""
        graph = {
            "nodes": [
                _start_node(),
                _llm_node("llm_1"),
                _llm_node("orphan"),  # 孤立
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "llm_1"),
                _edge("llm_1", "end_1"),
                # orphan 无连线
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        msg = str(cm.exception)
        self.assertTrue("orphan" in msg or "孤立" in msg, f"错误信息应提及孤立节点: {msg}")

    def test_llm_missing_profile_raises(self):
        """llm 节点 config 非空但缺 modelProfileCode，校验报错。"""
        graph = {
            "nodes": [
                _start_node(),
                # config 非空（避免触发"缺少配置信息"），但无 modelProfileCode
                {"id": "llm_1", "type": "llm", "name": "LLM", "config": {"prompt": "hi"}},
                _end_node(),
            ],
            "edges": [_edge("start_1", "llm_1"), _edge("llm_1", "end_1")],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("模型", str(cm.exception))

    def test_llm_missing_config_raises(self):
        """llm 节点缺 config，校验报错（错误信息含节点 name）。"""
        graph = {
            "nodes": [
                _start_node(),
                {"id": "llm_1", "type": "llm", "name": "LLM"},  # 无 config
                _end_node(),
            ],
            "edges": [_edge("start_1", "llm_1"), _edge("llm_1", "end_1")],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("LLM", str(cm.exception))
        self.assertIn("配置", str(cm.exception))

    def test_invalid_top_level_structure_raises(self):
        """空节点列表校验报错（缺 start 节点）。"""
        with self.assertRaises(ValueError):
            validate_graph({"nodes": [], "edges": []})
        with self.assertRaises(ValueError):
            validate_graph({"nodes": []})  # 缺 edges → 仍因缺 start 报错

    def test_edge_missing_source_or_target_raises(self):
        """连线缺 source 或 target，校验报错。"""
        graph = {
            "nodes": [_start_node(), _end_node()],
            "edges": [{"id": "e1", "source": "start_1"}],  # 缺 target
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("source", str(cm.exception).lower())


class CompileGraphTestCase(unittest.TestCase):
    """compile_graph 编译测试。"""

    def test_valid_graph_returns_compilable_builder(self):
        """合法图编译返回 StateGraph builder，可调用 .compile()。"""
        builder = WorkflowCompiler.compile_graph(_simple_graph())
        self.assertIsNotNone(builder)
        compiled = builder.compile()
        self.assertIsNotNone(compiled)

    def test_start_node_skipped_in_builder(self):
        """start 节点在编译时被跳过（不进入 builder.nodes）。"""
        builder = WorkflowCompiler.compile_graph(_simple_graph())
        node_ids = set(builder.nodes.keys())
        self.assertNotIn("start_1", node_ids)
        self.assertIn("llm_1", node_ids)
        self.assertIn("end_1", node_ids)

    def test_topology_chain_nodes_registered(self):
        """start → a → b → end 图，builder 包含 a / b / end，不包含 start。"""
        graph = {
            "nodes": [
                _start_node("start_1"),
                _llm_node("a"),
                _llm_node("b"),
                _end_node("end_1"),
            ],
            "edges": [
                _edge("start_1", "a"),
                _edge("a", "b"),
                _edge("b", "end_1"),
            ],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        node_ids = set(builder.nodes.keys())
        self.assertIn("a", node_ids)
        self.assertIn("b", node_ids)
        self.assertIn("end_1", node_ids)
        self.assertNotIn("start_1", node_ids)

    def test_execution_follows_topology_order(self):
        """start → a → b → end 图，node_runner 实际执行顺序为 a → b → end_1。"""
        call_order: list[str] = []

        async def recorder(inputs, config):
            call_order.append(config["id"])
            return {"output": "ok"}

        graph = {
            "nodes": [
                _start_node("start_1"),
                _llm_node("a"),
                _llm_node("b"),
                _end_node("end_1"),
            ],
            "edges": [
                _edge("start_1", "a"),
                _edge("a", "b"),
                _edge("b", "end_1"),
            ],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        compiled = builder.compile()

        with patch.object(compiler_mod.node_registry, "get", return_value=recorder):
            asyncio.run(
                compiled.ainvoke({"variables": {}, "messages": [], "current_node": "start_1"})
            )

        self.assertEqual(call_order, ["a", "b", "end_1"])

    def test_loop_body_group_skipped_in_builder(self):
        """loop_body_group 作为视觉容器被跳过，体节点编译进子图，不进入主图 builder。"""
        graph = {
            "nodes": [
                _start_node("start_1"),
                {
                    "id": "loop_1",
                    "type": "loop_controller",
                    "name": "Loop",
                    "config": {"bodyGroupId": "group_1"},
                },
                {
                    "id": "group_1",
                    "type": "loop_body_group",
                    "name": "Group",
                    "config": {"controllerNodeId": "loop_1"},
                },
                {
                    "id": "body_1",
                    "type": "llm",
                    "name": "Body LLM",
                    "config": {"modelProfileCode": "p1"},
                    "parentNode": "group_1",
                },
                _end_node("end_1"),
            ],
            "edges": [
                _edge("start_1", "loop_1"),
                _edge("loop_1", "group_1"),
                _edge("loop_1", "end_1"),  # loop 退出边
                _edge("body_1", "loop_1"),  # 回边
            ],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        node_ids = set(builder.nodes.keys())
        self.assertNotIn("group_1", node_ids, "loop_body_group 应被跳过")
        self.assertNotIn("body_1", node_ids, "子图体节点应被编译进子图，不进入主图")
        self.assertIn("loop_1", node_ids, "loop_controller 应在主图中")
        self.assertIn("end_1", node_ids, "end 节点应在主图中")
        self.assertNotIn("start_1", node_ids, "start 节点应被跳过")

    def test_invalid_graph_raises(self):
        """非法图（缺 start）编译时抛 ValueError。"""
        graph = {
            "nodes": [_llm_node("llm_1"), _end_node()],
            "edges": [_edge("llm_1", "end_1")],
        }
        with self.assertRaises(ValueError):
            WorkflowCompiler.compile_graph(graph)

    def test_invalid_top_level_raises(self):
        """顶层结构不合法，编译时抛 ValueError。"""
        with self.assertRaises(ValueError):
            WorkflowCompiler.compile_graph({"nodes": []})
        with self.assertRaises(ValueError):
            WorkflowCompiler.compile_graph("not a dict")

    def test_node_registry_contains_builtin_executors(self):
        """compile_graph 触发 import 后，node_registry 包含内置执行器（llm/end 等）。"""
        WorkflowCompiler.compile_graph(_simple_graph())
        self.assertIsNotNone(node_registry.get("llm"))
        self.assertIsNotNone(node_registry.get("end"))
        self.assertIsNotNone(node_registry.get("condition"))
        self.assertIsNotNone(node_registry.get("switch"))
        self.assertIsNotNone(node_registry.get("loop_controller"))

    def test_unregistered_node_type_raises_at_runtime(self):
        """编译时使用未注册的节点类型，运行时 node_runner 抛 ValueError。"""
        graph = {
            "nodes": [
                _start_node("start_1"),
                {
                    "id": "x_1",
                    "type": "totally_unknown_type",
                    "name": "X",
                    "config": {},
                },
                _end_node("end_1"),
            ],
            "edges": [_edge("start_1", "x_1"), _edge("x_1", "end_1")],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        compiled = builder.compile()

        async def _run():
            await compiled.ainvoke(
                {"variables": {}, "messages": [], "current_node": "start_1"}
            )

        # node_registry.get 返回 None（未注册），node_runner 应抛 ValueError
        with self.assertRaises(ValueError) as cm:
            asyncio.run(_run())
        self.assertIn("totally_unknown_type", str(cm.exception))


class NodeExecutorRegistryTestCase(unittest.TestCase):
    """NodeExecutorRegistry 注册表测试。"""

    def test_register_and_get(self):
        """注册后可通过 get 取回执行器。"""
        registry = NodeExecutorRegistry()

        async def executor(state, config):
            return {"output": "ok"}

        registry.register("custom_type", executor)
        self.assertIs(registry.get("custom_type"), executor)

    def test_get_unregistered_returns_none(self):
        """未注册类型返回 None。"""
        registry = NodeExecutorRegistry()
        self.assertIsNone(registry.get("not_registered"))

    def test_register_overrides_existing(self):
        """重复注册同类型会覆盖旧执行器。"""
        registry = NodeExecutorRegistry()

        async def v1(state, config):
            return {"v": 1}

        async def v2(state, config):
            return {"v": 2}

        registry.register("t", v1)
        self.assertIs(registry.get("t"), v1)
        registry.register("t", v2)
        self.assertIs(registry.get("t"), v2)


class NodeExecutionErrorTestCase(unittest.TestCase):
    """NodeExecutionError 异常测试。"""

    def test_carries_node_id_and_attempts(self):
        """异常携带 node_id / attempts / cause，且消息包含关键信息。"""
        cause = RuntimeError("boom")
        err = NodeExecutionError("node_42", 3, cause)
        self.assertEqual(err.node_id, "node_42")
        self.assertEqual(err.attempts, 3)
        self.assertIs(err.cause, cause)
        msg = str(err)
        self.assertIn("node_42", msg)
        self.assertIn("3", msg)

    def test_is_exception_subclass(self):
        """NodeExecutionError 是 Exception 子类，可被 except Exception 捕获。"""
        err = NodeExecutionError("n", 1, RuntimeError("x"))
        with self.assertRaises(Exception):
            raise err

    def test_node_id_attr_accessible_via_getattr(self):
        """上层用 getattr(err, 'node_id', None) 取值时返回正确 node_id。"""
        err = NodeExecutionError("node_99", 2, RuntimeError("x"))
        self.assertEqual(getattr(err, "node_id", None), "node_99")
        # 普通异常无 node_id → getattr 返回 None
        self.assertIsNone(getattr(RuntimeError("x"), "node_id", None))


class ConstantsTestCase(unittest.TestCase):
    """compiler 常量集合测试。"""

    def test_conditional_node_types(self):
        """条件分流节点类型集合内容正确。"""
        self.assertEqual(CONDITIONAL_NODE_TYPES, {"condition", "intent_classifier", "switch"})

    def test_subgraph_node_types(self):
        """子图执行节点类型集合内容正确。"""
        self.assertEqual(SUBGRAPH_NODE_TYPES, {"loop_controller", "batch_processor"})

    def test_untestable_node_types_contains_expected(self):
        """UNTESTABLE_NODE_TYPES 包含所有不支持单节点测试的类型。"""
        for t in (
            "start",
            "end",
            "loop_controller",
            "batch_processor",
            "human_input",
            "loop_body_group",
        ):
            self.assertIn(t, UNTESTABLE_NODE_TYPES)

    def test_conditional_disjoint_from_subgraph(self):
        """条件节点与子图节点类型互斥（语义不同）。"""
        self.assertTrue(CONDITIONAL_NODE_TYPES.isdisjoint(SUBGRAPH_NODE_TYPES))


if __name__ == "__main__":
    unittest.main()
