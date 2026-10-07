"""Phase 2：节点级自动重试 + failed_node_id 测试。

- 全局默认 / 节点 config 覆盖 / 指数退避 / 重试耗尽抛 NodeExecutionError（携带 node_id）
- failed_node_id 字段持久化
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel

import app.modules.workflow.service.node_executors  # noqa: F401  (import 副作用：注册执行器与幂等元数据)
from app.core.config import settings
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service import compiler as compiler_mod
from app.modules.workflow.service.compiler import NodeExecutionError, WorkflowCompiler


async def _fake_sleep(delay):
    """退避等待置零：只验证抖动参数与调用，不真等。"""
    return None


class NodeRunnerRetryTestCase(unittest.TestCase):
    """节点级重试：全局默认 + 节点覆盖 + 指数退避 + NodeExecutionError。"""

    def _make_runner(self, config: dict):
        return WorkflowCompiler.create_node_runner("n1", "llm", config)

    def _run(self, runner):
        state = {"variables": {}, "current_node": "start"}
        return asyncio.run(runner(state))

    def _patch_helpers(self):
        """隔离重试逻辑：跳过输入映射 / 输出 delta 的真实处理（三期B5 起为 compute_output_delta）。"""
        return (
            patch.object(compiler_mod, "resolve_node_inputs", return_value={}),
            patch.object(compiler_mod, "compute_output_delta", side_effect=lambda u, m: dict(u or {})),
        )

    def test_no_retry_by_default_first_failure_raises(self):
        """全局默认 max_attempts=1：首次失败即抛 NodeExecutionError，携带 node_id。"""

        async def failer(inputs, config):
            raise RuntimeError("boom")

        p1, p2 = self._patch_helpers()
        with p1, p2, patch.object(compiler_mod.node_registry, "get", return_value=failer):
            runner = self._make_runner({})
            with self.assertRaises(NodeExecutionError) as cm:
                self._run(runner)
        self.assertEqual(cm.exception.node_id, "n1")
        self.assertEqual(cm.exception.attempts, 1)

    def test_retry_succeeds_after_transient_failures(self):
        """max_attempts=3：前 2 次失败、第 3 次成功 → 正常返回 updates。"""
        calls = 0

        async def flaky(inputs, config):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("transient")
            return {"output": "ok"}

        p1, p2 = self._patch_helpers()
        with p1, p2, patch.object(compiler_mod.node_registry, "get", return_value=flaky):
            runner = self._make_runner({"retry_max_attempts": 3, "retry_backoff_base": 0.0})
            result = self._run(runner)
        self.assertEqual(calls, 3)
        self.assertEqual(result["current_node"], "n1")
        self.assertEqual(result["variables"]["output"], "ok")

    def test_node_config_overrides_global_default(self):
        """节点 config 的 retry_max_attempts 覆盖 settings 全局默认。"""
        calls = 0

        async def always_fail(inputs, config):
            nonlocal calls
            calls += 1
            raise RuntimeError("always")

        p1, p2 = self._patch_helpers()
        with (
            p1,
            p2,
            patch.object(compiler_mod.node_registry, "get", return_value=always_fail),
            patch.object(settings, "WORKFLOW_NODE_RETRY_MAX_ATTEMPTS", 5),
        ):
            runner = self._make_runner({"retry_max_attempts": 2, "retry_backoff_base": 0.0})
            with self.assertRaises(NodeExecutionError) as cm:
                self._run(runner)
        self.assertEqual(calls, 2)
        self.assertEqual(cm.exception.attempts, 2)

    def test_uses_global_default_when_node_config_absent(self):
        """节点 config 未配 retry → 用 settings 全局默认。"""
        calls = 0

        async def always_fail(inputs, config):
            nonlocal calls
            calls += 1
            raise RuntimeError("always")

        p1, p2 = self._patch_helpers()
        with (
            p1,
            p2,
            patch.object(compiler_mod.node_registry, "get", return_value=always_fail),
            patch.object(settings, "WORKFLOW_NODE_RETRY_MAX_ATTEMPTS", 4),
            patch.object(settings, "WORKFLOW_NODE_RETRY_BACKOFF_BASE", 0.0),
        ):
            runner = self._make_runner({})
            with self.assertRaises(NodeExecutionError):
                self._run(runner)
        self.assertEqual(calls, 4)

    def test_attempts_clamped_to_at_least_one(self):
        """max_attempts 下限为 1（即使配 0 也至少执行 1 次）。"""
        calls = 0

        async def always_fail(inputs, config):
            nonlocal calls
            calls += 1
            raise RuntimeError("always")

        p1, p2 = self._patch_helpers()
        with p1, p2, patch.object(compiler_mod.node_registry, "get", return_value=always_fail):
            runner = self._make_runner({"retry_max_attempts": 0, "retry_backoff_base": 0.0})
            with self.assertRaises(NodeExecutionError):
                self._run(runner)
        self.assertEqual(calls, 1)

    def test_backoff_jitter_bounds(self):
        """指数退避叠加 ±50% 全抖动（三期B6 / WF-P2-3）：uniform(0.5, 1.5) 乘入。"""
        jitter_calls = []

        async def failer(inputs, config):
            raise RuntimeError("boom")

        captured_uniform = patch("random.uniform", side_effect=lambda lo, hi: (jitter_calls.append((lo, hi)), 1.0)[1])
        p1, p2 = self._patch_helpers()
        with (
            p1,
            p2,
            patch.object(compiler_mod.node_registry, "get", return_value=failer),
            captured_uniform,
            patch("asyncio.sleep", new=_fake_sleep),
        ):
            runner = self._make_runner({"retry_max_attempts": 2, "retry_backoff_base": 2.0})
            with self.assertRaises(NodeExecutionError):
                self._run(runner)
        self.assertEqual(jitter_calls, [(0.5, 1.5)])

    def test_graph_interrupt_not_retried(self):
        """GraphInterrupt（人工审批中断）必须原样上抛：不重试、不包装为 NodeExecutionError。

        回归守护：create_node_runner 的 except Exception 曾吞掉该控制流信号，
        导致 human_input 节点永远无法进入 paused，实例被误判为 failed。
        """
        from langgraph.errors import GraphInterrupt

        calls = 0

        async def interrupter(inputs, config):
            nonlocal calls
            calls += 1
            raise GraphInterrupt()

        p1, p2 = self._patch_helpers()
        with p1, p2, patch.object(compiler_mod.node_registry, "get", return_value=interrupter):
            # 即使配了 3 次重试，也不得重试控制流信号
            runner = self._make_runner({"retry_max_attempts": 3, "retry_backoff_base": 0.0})
            with self.assertRaises(GraphInterrupt):
                self._run(runner)
        self.assertEqual(calls, 1)

    def test_graph_drained_not_retried(self):
        """GraphDrained（优雅停机信号，同为 GraphBubbleUp 子类）同样不得被重试或包装。"""
        from langgraph.errors import GraphDrained

        calls = 0

        async def drainer(inputs, config):
            nonlocal calls
            calls += 1
            raise GraphDrained("shutdown")

        p1, p2 = self._patch_helpers()
        with p1, p2, patch.object(compiler_mod.node_registry, "get", return_value=drainer):
            runner = self._make_runner({"retry_max_attempts": 3, "retry_backoff_base": 0.0})
            with self.assertRaises(GraphDrained):
                self._run(runner)
        self.assertEqual(calls, 1)


class IdempotencyRetryGuardTestCase(unittest.TestCase):
    """非幂等节点强制 max_attempts=1（三期B6 / WF-P2-3）：重试 = 整体重跑/重复计费。

    依赖真实注册表元数据：import node_executors 触发注册副作用。
    """

    def _run_with_type(self, node_type: str, config: dict):
        """以指定 node_type 构建 runner 并执行（executor patch 为恒失败），返回 (异常, 调用次数)。

        仅 patch registry.get（executor 实现），node_type 元数据查真实注册表。
        """
        calls = 0

        async def failer(inputs, cfg):
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        state = {"variables": {}, "current_node": "start"}

        async def _go():
            runner = WorkflowCompiler.create_node_runner("n1", node_type, config)
            try:
                await runner(state)
                return None, calls
            except NodeExecutionError as e:
                return e, calls

        with patch.object(compiler_mod.node_registry, "get", return_value=failer):
            return asyncio.run(_go())

    def test_non_idempotent_forced_single_attempt(self):
        """image_generator（注册表 idempotent=False）请求 3 次重试 → 仅执行 1 次。"""
        err, calls = self._run_with_type("image_generator", {"retry_max_attempts": 3})
        self.assertEqual(calls, 1)
        self.assertEqual(err.attempts, 1)

    def test_idempotent_node_retries_normally(self):
        """幂等节点（llm）同 config 正常重试到耗尽。"""
        err, calls = self._run_with_type("llm", {"retry_max_attempts": 3, "retry_backoff_base": 0.0})
        self.assertEqual(calls, 3)
        self.assertEqual(err.attempts, 3)

    def test_unregistered_type_defaults_idempotent(self):
        """未注册类型防御性默认幂等（执行前另有拦截，此处仅锁定 is_idempotent 默认）。"""
        self.assertTrue(compiler_mod.node_registry.is_idempotent("__no_such_type__"))

    def test_registry_metadata_declared(self):
        """非幂等声明清单：image_generator / loop_controller / batch_processor。

        deprecated `tool` 已随三期B7 下架（不再注册，迁移见 test_workflow_tool_migration）。
        """
        registry = compiler_mod.node_registry
        for node_type in ("image_generator", "loop_controller", "batch_processor"):
            self.assertFalse(registry.is_idempotent(node_type), node_type)
        self.assertIsNone(registry.get("tool"))
        self.assertFalse(registry.is_deprecated("llm"))


class RunNodeStandaloneTestCase(unittest.TestCase):
    """单节点测试执行体（run_node_standalone）：与整图执行共享重试/输出映射语义（修 P0-1）。

    回归守护：test_node 此前直连 executor，测不到重试与 output_mappings——
    「节点测试通过 ≠ 整图能跑通」。改造后两条路径共用 _invoke_executor_with_retry。
    """

    def _run_standalone(self, config: dict, mock_variables: dict | None = None):
        return asyncio.run(WorkflowCompiler.run_node_standalone("n1", "llm", config, mock_variables or {}))

    def test_retry_applied_in_standalone(self):
        """单节点测试同样走重试：前 2 次瞬时失败、第 3 次成功。"""
        calls = 0

        async def flaky(inputs, config):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("transient")
            return {"output": "ok"}

        with patch.object(compiler_mod.node_registry, "get", return_value=flaky):
            result = self._run_standalone({"retry_max_attempts": 3, "retry_backoff_base": 0.0})
        self.assertEqual(calls, 3)  # 直连 executor 的旧实现 calls=1，此处验证重试语义生效
        self.assertEqual(result, {"output": "ok"})

    def test_bubble_up_not_swallowed(self):
        """控制流信号（GraphInterrupt）在单节点测试中同样原样上抛、不重试。"""
        from langgraph.errors import GraphInterrupt

        calls = 0

        async def interrupter(inputs, config):
            nonlocal calls
            calls += 1
            raise GraphInterrupt()

        with patch.object(compiler_mod.node_registry, "get", return_value=interrupter):
            with self.assertRaises(GraphInterrupt):
                self._run_standalone({"retry_max_attempts": 3, "retry_backoff_base": 0.0})
        self.assertEqual(calls, 1)

    def test_human_input_interrupt_via_minimal_graph(self):
        """三期B6 最小图通道：human_input 真实执行器（interrupt）经图运行时转为
        __interrupt__ updates 事件，standalone 检测后转译 GraphInterrupt 上抛。"""
        from langgraph.errors import GraphInterrupt

        with self.assertRaises(GraphInterrupt):
            asyncio.run(WorkflowCompiler.run_node_standalone("h1", "human_input", {"message": "请审批"}, {}))

    def test_retry_exhausted_raises_node_execution_error(self):
        """重试耗尽抛 NodeExecutionError（携带 node_id），供前端显示可读错误。"""

        async def always_fail(inputs, config):
            raise RuntimeError("boom")

        with patch.object(compiler_mod.node_registry, "get", return_value=always_fail):
            with self.assertRaises(NodeExecutionError) as cm:
                self._run_standalone({"retry_max_attempts": 2, "retry_backoff_base": 0.0})
        self.assertEqual(cm.exception.node_id, "n1")
        self.assertEqual(cm.exception.attempts, 2)

    def test_output_mappings_applied_and_diffed(self):
        """output_mappings 写回后按差集返回增量：mock 键不出现在结果中。"""
        config = {"output_mappings": {"result": "variables.final"}}

        async def ok(inputs, config):
            return {"result": "ok"}

        with patch.object(compiler_mod.node_registry, "get", return_value=ok):
            result = self._run_standalone(config, {"input_1": "hi"})
        # updates 经映射写到 final；mock 的 input_1 不回显
        self.assertEqual(result, {"final": "ok"})

    def test_no_mappings_returns_updates_directly(self):
        """无 output_mappings：updates 即增量（与旧 test_node 契约一致）。"""

        async def ok(inputs, config):
            return {"output": 42}

        with patch.object(compiler_mod.node_registry, "get", return_value=ok):
            result = self._run_standalone({}, {"q": "hi"})
        self.assertEqual(result, {"output": 42})

    def test_same_value_overwrite_not_reported_as_increment(self):
        """updates 与 mock 同键同值：不误报为增量（差集语义）。"""

        async def echo(inputs, config):
            return {"q": "hi", "new": 1}

        with patch.object(compiler_mod.node_registry, "get", return_value=echo):
            result = self._run_standalone({}, {"q": "hi"})
        self.assertEqual(result, {"new": 1})


class FailedNodeIdPersistTestCase(unittest.TestCase):
    """failed_node_id 字段持久化 + NodeExecutionError 携带 node_id。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_node_execution_error_carries_node_id(self):
        """NodeExecutionError 的 node_id 可被上层 getattr 取用（workflow_tasks except 块的取值方式）。"""
        err = NodeExecutionError("node_42", 3, RuntimeError("cause"))
        self.assertEqual(err.node_id, "node_42")
        self.assertEqual(err.attempts, 3)
        self.assertEqual(getattr(err, "node_id", None), "node_42")
        # 普通异常无 node_id → getattr 返回 None（超时等场景留空）
        self.assertIsNone(getattr(RuntimeError("x"), "node_id", None))

    def test_failed_node_id_field_persists(self):
        """WorkflowInstance.failed_node_id 字段可写入并读回。"""
        definition = WorkflowDefinition(
            code="wf1", name="WF1", graph_json="{}", is_active=True, current_version_id=1, user_id=1
        )
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id="t1",
            status="failed",
            state_data="{}",
            user_id=1,
            failed_node_id="node_99",
        )
        self.session.add(instance)
        self.session.commit()
        with Session(self.engine) as verify:
            refreshed = verify.get(WorkflowInstance, instance.id)
            self.assertEqual(refreshed.failed_node_id, "node_99")


if __name__ == "__main__":
    unittest.main()
