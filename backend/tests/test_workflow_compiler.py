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
    SUBGRAPH_NODE_TYPES,
    UNTESTABLE_NODE_TYPES,
    NodeExecutionError,
    NodeExecutorRegistry,
    WorkflowCompiler,
    node_registry,
    render_template,
    safe_eval,
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
            asyncio.run(compiled.ainvoke({"variables": {}, "current_node": "start_1"}))

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
                    # 三期B6 schema 校验要求必填 listVariable（此前简化图缺省）
                    "config": {"bodyGroupId": "group_1", "listVariable": "list_variable"},
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
            await compiled.ainvoke({"variables": {}, "current_node": "start_1"})

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
        with self.assertRaises(Exception):  # noqa: B017 —— 测试意图即验证 except Exception 宽捕获
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


class RenderTemplateUnicodeTestCase(unittest.TestCase):
    """模板渲染中文变量名（前端 sanitizeLabel 会保留中文，后端必须同样识别）。"""

    def test_render_template_unicode_var(self):
        """中文变量名可被插值；ASCII 与点号路径行为不变。"""
        variables = {"意图分类_output": "分类结果A", "llm_output": {"text": "hello"}, "甲": {"乙": [9]}}

        # 中文变量名：曾因正则字符类不含 CJK 而被静默跳过
        self.assertEqual(
            render_template("请根据 {意图分类_output} 生成内容", variables),
            "请根据 分类结果A 生成内容",
        )
        # 中文 + 点号深层路径
        self.assertEqual(render_template("{甲.乙}", variables), "[9]")
        # 回归：ASCII 与嵌套字典不受影响
        self.assertEqual(render_template("v={llm_output.text}", variables), "v=hello")
        # 未定义变量 → 空串（既有语义）
        self.assertEqual(render_template("x={不存在的变量}", variables), "x=")


class SafeEvalTestCase(unittest.TestCase):
    """SafeEvaluator 表达式能力（条件路由 / 变量赋值 / 数据转换 三处共用）。"""

    def test_safe_eval_container_literals(self):
        """集合/序列/字典字面量：`in [...]`、`not in (...)`、`== {...}` 等常用判定不再报错。

        回归守护：曾因缺 ast.List/Tuple/Set/Dict 分支而抛
        「不支持的 AST 节点类型」，条件路由静默回落 false。
        """
        ctx = {"status": "success", "user_type": 3, "tags": ["a", "b"], "d": {"k": 1}}
        self.assertTrue(safe_eval("status in ['success','approved']", ctx))
        self.assertTrue(safe_eval("user_type not in (1, 2)", ctx))
        self.assertTrue(safe_eval("tags == ['a','b']", ctx))
        self.assertTrue(safe_eval("d == {'k': 1}", ctx))
        self.assertTrue(safe_eval("status in {'success', 'ok'}", ctx))
        # 回归：既有能力不受影响
        self.assertTrue(safe_eval("len(tags) == 2 and status == 'success'", ctx))

    def test_safe_eval_ifexp_joinedstr(self):
        """三元表达式与 f-string（同为原兜底分支的缺口）。"""
        ctx = {"count": 3, "name": "阿苏"}
        self.assertEqual(safe_eval("'a' if count > 1 else 'b'", ctx), "a")
        self.assertEqual(safe_eval("'b' if count > 5 else 'a'", ctx), "a")
        self.assertEqual(safe_eval('f"v={count}"', ctx), "v=3")
        self.assertEqual(safe_eval('f"{name} 有 {count} 条"', ctx), "阿苏 有 3 条")
        self.assertEqual(safe_eval('f"{count:.2f}"', ctx), "3.00")

    def test_safe_eval_keeps_security_boundary(self):
        """能力扩展不得放宽安全边界：未登记函数调用与字典解包仍被拒绝。"""
        with self.assertRaises(ValueError):
            safe_eval("__import__('os').system('ls')", {})
        with self.assertRaises(ValueError):
            safe_eval("{**{'a': 1}}", {})


# --- WF-P0-1 条件路由推导/注册拆分测试 ---

# 执行器经定义模块全局查找 run_ai_chat，patch 必须落在定义处（node_executors）
_MOCK_AI_CHAT_PATH = "app.modules.workflow.service.node_executors.run_ai_chat"


def _intent_node(node_id: str = "intent_1") -> dict:
    return {
        "id": node_id,
        "type": "intent_classifier",
        "name": f"Intent-{node_id}",
        "config": {
            "modelProfileCode": "p1",
            "intents": [
                {"id": "i1", "name": "A", "description": ""},
                {"id": "i2", "name": "B", "description": ""},
            ],
        },
    }


def _handle_edge(src: str, tgt: str, handle: str) -> dict:
    return {"id": f"e_{src}_{tgt}", "source": src, "target": tgt, "sourceHandle": handle}


class DeriveConditionalConfigTestCase(unittest.TestCase):
    """_derive_conditional_config：边推导结果必须写回返回的 config（WF-P0-1 核心）。"""

    def test_intent_target_route_written_back_by_id(self):
        node = _intent_node()
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("intent_1", "branch_a", "intent_i1")])
        self.assertEqual(cfg["intents"][0]["target_route"], "branch_a")

    def test_intent_numeric_index_fallback(self):
        """handle 携带的数字无法匹配任何 intent id 时，按下标回退。"""
        node = _intent_node()  # ids: i1 / i2，handle "intent_1" 的 rest="1" 不匹配任何 id
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("intent_1", "branch_b", "intent_1")])
        self.assertEqual(cfg["intents"][1]["target_route"], "branch_b")
        self.assertIsNone(cfg["intents"][0].get("target_route"))

    def test_intent_id_match_priority_over_index(self):
        """同一条边既可按 id 匹配又可按数字下标命中时，id 匹配优先（既有语义锚定）。"""
        node = _intent_node()
        node["config"]["intents"] = [{"id": "1", "name": "A"}, {"id": "i2", "name": "B"}]
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("intent_1", "branch_a", "intent_1")])
        self.assertEqual(cfg["intents"][0]["target_route"], "branch_a")
        self.assertIsNone(cfg["intents"][1].get("target_route"))

    def test_intent_default_handle_writes_default_route(self):
        node = _intent_node()
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("intent_1", "branch_c", "default")])
        self.assertEqual(cfg["default_route"], "branch_c")

    def test_switch_case_written_back(self):
        node = {
            "id": "switch_1",
            "type": "switch",
            "name": "Switch",
            "config": {"variable": "mode", "cases": [{"id": "c1", "value": "x"}]},
        }
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("switch_1", "branch_x", "case_c1")])
        self.assertEqual(cfg["cases"][0]["target_route"], "branch_x")

    def test_condition_fallback_written_back(self):
        """condition 双路由全靠边回退时，true_route/false_route 必须写回 config。"""
        node = {
            "id": "cond_1",
            "type": "condition",
            "name": "Cond",
            "config": {"expression": "1 == 1"},
        }
        edges = [_handle_edge("cond_1", "branch_a", "true"), _handle_edge("cond_1", "branch_b", "false")]
        cfg = compiler_mod._derive_conditional_config(node, edges)
        self.assertEqual(cfg["true_route"], "branch_a")
        self.assertEqual(cfg["false_route"], "branch_b")

    def test_condition_half_missing_filled_from_edge(self):
        """半缺形态：config 已有 falseRoute、true 靠边补齐——两者都应在返回值中。"""
        node = {
            "id": "cond_1",
            "type": "condition",
            "name": "Cond",
            "config": {"expression": "1 == 1", "falseRoute": "branch_b"},
        }
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("cond_1", "branch_a", "true")])
        self.assertEqual(cfg["true_route"], "branch_a")
        self.assertEqual(cfg["false_route"], "branch_b")

    def test_returns_fresh_copy_no_alias(self):
        """返回对象与输入 config 无共享引用（深拷贝契约）：改返回值不得影响原图。"""
        node = _intent_node()
        original = node["config"]
        cfg = compiler_mod._derive_conditional_config(node, [_handle_edge("intent_1", "branch_a", "intent_i1")])
        cfg["intents"][0]["target_route"] = "mutated"
        cfg["default_route"] = "mutated"
        self.assertIsNone(original["intents"][0].get("target_route"))
        self.assertNotIn("default_route", original)


class RegisterConditionalEdgesGuardsTestCase(unittest.TestCase):
    """_register_conditional_edges 的守卫语义（与重构前逐字节等价）。"""

    def test_condition_without_routes_rejected_at_validation(self):
        """condition 无任何路由：三期B6 起 validate_graph 拒绝（原「len(path_map)==1
        守卫 → 静默不注册条件边」语义被显式校验取代——静默终结即静默失败）。"""
        graph = {
            "nodes": [
                _start_node(),
                {"id": "cond_1", "type": "condition", "name": "Cond", "config": {"expression": "True"}},
                _end_node(),
            ],
            "edges": [_edge("start_1", "cond_1"), _edge("cond_1", "end_1")],
        }
        with self.assertRaises(ValueError) as cm:
            WorkflowCompiler.compile_graph(graph)
        self.assertIn("没有任何可解析的路由", str(cm.exception))

    def test_intent_with_config_default_still_registered(self):
        """intent 无任何边但有 config defaultRoute：仍注册条件边（END 兜底 + default）。"""
        intent = _intent_node()
        intent["config"]["defaultRoute"] = "end_1"
        graph = {
            "nodes": [_start_node(), intent, _end_node()],
            "edges": [_edge("start_1", "intent_1")],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        self.assertTrue(getattr(builder, "branches", {}).get("intent_1"))


class IntentRoutingHardGateTestCase(unittest.TestCase):
    """编译级硬门禁：判出意图 A 必须走 A 分支（修前执行器 config 无 target_route，恒走 default）。"""

    def _intent_graph(self) -> dict:
        return {
            "nodes": [
                _start_node(),
                _intent_node(),
                _llm_node("branch_a"),
                _llm_node("branch_b"),
                _llm_node("branch_c"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "intent_1"),
                _handle_edge("intent_1", "branch_a", "intent_i1"),
                _handle_edge("intent_1", "branch_b", "intent_i2"),
                _handle_edge("intent_1", "branch_c", "default"),
                _edge("branch_a", "end_1"),
                _edge("branch_b", "end_1"),
                _edge("branch_c", "end_1"),
            ],
        }

    def _run_graph(self, graph: dict, model_reply: str, variables: dict | None = None) -> list[str]:
        builder = WorkflowCompiler.compile_graph(graph)
        compiled = builder.compile()
        call_order: list[str] = []
        real_get = compiler_mod.node_registry.get

        def recording_get(node_type):
            real_executor = real_get(node_type)
            if node_type != "llm":
                return real_executor

            async def recorder(node_variables, config):
                call_order.append(config.get("id"))
                return {}

            return recorder

        with (
            patch.object(compiler_mod.node_registry, "get", new=recording_get),
            patch(_MOCK_AI_CHAT_PATH, return_value=model_reply),
        ):
            asyncio.run(compiled.ainvoke({"variables": variables or {"query": "hello"}, "current_node": "start_1"}))
        return call_order

    def test_named_intent_routes_to_named_branch(self):
        """判出意图 A → 走 A 分支（本用例在修复前失败且 call_order==['branch_c']）。"""
        call_order = self._run_graph(self._intent_graph(), "A")
        self.assertEqual(call_order, ["branch_a"])

    def test_unknown_intent_routes_to_default(self):
        """未命中任何意图 → 走 default 分支。"""
        call_order = self._run_graph(self._intent_graph(), "完全未知的意图xyz")
        self.assertEqual(call_order, ["branch_c"])

    def test_intent_inside_loop_body_routes_to_named_branch(self):
        """体子图内的 intent 同样命中具名分支（守护 _compile_body_graph 的推导前置）。"""
        loop_node = {
            "id": "loop_1",
            "type": "loop_controller",
            "name": "Loop",
            "config": {
                "loopBodyRoute": "intent_1",
                "listVariable": "items",
                "itemVariable": "item",
                "outputVariable": "results",
            },
        }
        graph = {
            "nodes": [
                _start_node(),
                loop_node,
                _intent_node("intent_1"),
                _llm_node("branch_a"),
                _llm_node("branch_c"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "loop_1"),
                _edge("loop_1", "end_1"),
                _handle_edge("intent_1", "branch_a", "intent_i1"),
                _handle_edge("intent_1", "branch_c", "default"),
                _edge("branch_a", "loop_1"),
                _edge("branch_c", "loop_1"),
            ],
        }
        call_order = self._run_graph(graph, "A", variables={"items": ["x"], "query": "hello"})
        self.assertEqual(call_order, ["branch_a"])


class ConditionEdgeFallbackActivationTestCase(unittest.TestCase):
    """condition 双路由全靠边回退（config 无 trueRoute/falseRoute）的图必须可用。

    修复前：回退结果只存编译局部变量，router 读 config 拿到 None，表达式为真时
    返回 None → path_map 无此键 → LangGraph 路由报错。derive 写回后恢复可用。
    """

    def test_condition_routes_via_source_handle_only(self):
        cond = {"id": "cond_1", "type": "condition", "name": "Cond", "config": {"expression": "1 == 1"}}
        graph = {
            "nodes": [
                _start_node(),
                cond,
                _llm_node("branch_a"),
                _llm_node("branch_b"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "cond_1"),
                _handle_edge("cond_1", "branch_a", "true"),
                _handle_edge("cond_1", "branch_b", "false"),
                _edge("branch_a", "end_1"),
                _edge("branch_b", "end_1"),
            ],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        compiled = builder.compile()
        call_order: list[str] = []
        real_get = compiler_mod.node_registry.get

        def recording_get(node_type):
            real_executor = real_get(node_type)
            if node_type != "llm":
                return real_executor

            async def recorder(node_variables, config):
                call_order.append(config.get("id"))
                return {}

            return recorder

        with patch.object(compiler_mod.node_registry, "get", new=recording_get):
            asyncio.run(compiled.ainvoke({"variables": {}, "current_node": "start_1"}))
        self.assertEqual(call_order, ["branch_a"])


class BodyZeroOutEdgeConditionalGuardTestCase(unittest.TestCase):
    """R1 守护：体子图零出边的条件节点不注册条件边（分支自然终结，不得变为跳 default 的活分支）。"""

    def test_zero_out_edge_condition_in_body_registers_no_branch(self):
        from app.modules.workflow.service.compiler import _compile_body_graph

        cond = {"id": "cond_1", "type": "condition", "name": "C", "config": {"expression": "True"}}
        builder = _compile_body_graph([cond], [], "cond_1", "loop_1")
        self.assertFalse(getattr(builder, "branches", {}).get("cond_1"))


class MultiNodeLoopBodyCompileTestCase(unittest.TestCase):
    """多节点循环体（体内部有连线）必须可编译可执行。

    回归锚：_validate_subgraph_boundaries 第二分支曾缺 source not in body_node_ids，
    任何体节点数 ≥2 的循环体都被误判为「循环外节点直连体内」而无法编译。
    """

    def test_two_node_body_compiles_and_executes(self):
        graph = {
            "nodes": [
                _start_node(),
                {
                    "id": "loop_1",
                    "type": "loop_controller",
                    "name": "Loop",
                    "config": {
                        "loopBodyRoute": "body_a",
                        "listVariable": "items",
                        "itemVariable": "item",
                        "outputVariable": "results",
                    },
                },
                _llm_node("body_a"),
                _llm_node("body_b"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "loop_1"),
                _edge("loop_1", "end_1"),
                _edge("body_a", "body_b"),  # 体内部连线
                _edge("body_b", "loop_1"),  # 回边
            ],
        }
        builder = WorkflowCompiler.compile_graph(graph)
        compiled = builder.compile()
        call_order: list[str] = []
        real_get = compiler_mod.node_registry.get

        def recording_get(node_type):
            real_executor = real_get(node_type)
            if node_type != "llm":
                return real_executor

            async def recorder(node_variables, config):
                call_order.append(config.get("id"))
                return {}

            return recorder

        with patch.object(compiler_mod.node_registry, "get", new=recording_get):
            asyncio.run(compiled.ainvoke({"variables": {"items": ["x", "y"]}, "current_node": "start_1"}))
        # 2 项 × 2 体节点，串联执行
        self.assertEqual(call_order, ["body_a", "body_b", "body_a", "body_b"])


class BodyInterruptForbiddenTestCase(unittest.TestCase):
    """WF-P1-4：循环/批处理体不得包含中断类节点（体子图无断点，中断不可恢复）。"""

    def _human_node(self, node_id: str = "hi", parent: str | None = None) -> dict:
        node = {"id": node_id, "type": "human_input", "name": "审批", "config": {"message": "确认？"}}
        if parent:
            node["parentNode"] = parent
        return node

    def test_parent_mode_body_with_human_input_raises(self):
        graph = {
            "nodes": [
                _start_node(),
                {"id": "loop_1", "type": "loop_controller", "name": "Loop", "config": {"bodyGroupId": "group_1"}},
                {"id": "group_1", "type": "loop_body_group", "name": "Group", "config": {"controllerNodeId": "loop_1"}},
                self._human_node(parent="group_1"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "loop_1"),
                _edge("loop_1", "group_1"),
                _edge("loop_1", "end_1"),
                _edge("hi", "loop_1"),
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("中断类节点", str(cm.exception))

    def test_bfs_mode_body_with_human_input_raises(self):
        graph = {
            "nodes": [
                _start_node(),
                {
                    "id": "loop_1",
                    "type": "loop_controller",
                    "name": "Loop",
                    "config": {"loopBodyRoute": "hi", "listVariable": "items"},
                },
                self._human_node(),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "loop_1"),
                _edge("loop_1", "end_1"),
                _edge("hi", "loop_1"),
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_graph(graph)
        self.assertIn("中断类节点", str(cm.exception))

    def test_main_graph_human_input_still_allowed(self):
        """反向锚：主图（非循环体）的 human_input 不受影响。"""
        graph = {
            "nodes": [
                _start_node(),
                _llm_node("llm_1"),
                self._human_node(),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "llm_1"),
                _edge("llm_1", "hi"),
                _edge("hi", "end_1"),
            ],
        }
        validate_graph(graph)  # 不抛即通过


if __name__ == "__main__":
    unittest.main()
