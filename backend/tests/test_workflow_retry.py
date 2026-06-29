"""Phase 2：节点级自动重试 + failed_node_id 测试。

- 全局默认 / 节点 config 覆盖 / 指数退避 / 重试耗尽抛 NodeExecutionError（携带 node_id）
- failed_node_id 字段持久化
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service import compiler as compiler_mod
from app.modules.workflow.service.compiler import NodeExecutionError, WorkflowCompiler


class NodeRunnerRetryTestCase(unittest.TestCase):
    """节点级重试：全局默认 + 节点覆盖 + 指数退避 + NodeExecutionError。"""

    def _make_runner(self, config: dict):
        return WorkflowCompiler.create_node_runner("n1", "llm", config)

    def _run(self, runner):
        state = {"variables": {}, "current_node": "start"}
        return asyncio.run(runner(state))

    def _patch_helpers(self):
        """隔离重试逻辑：跳过输入映射 / 输出合并的真实处理。"""
        return (
            patch.object(compiler_mod, "resolve_node_inputs", return_value={}),
            patch.object(compiler_mod, "apply_output_mappings", side_effect=lambda v, u, m: {**v, **u}),
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


class FailedNodeIdPersistTestCase(unittest.TestCase):
    """failed_node_id 字段持久化 + NodeExecutionError 携带 node_id。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
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
