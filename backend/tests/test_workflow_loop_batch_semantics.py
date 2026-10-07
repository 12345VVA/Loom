"""二期 B3：loop/batch collect_keys / persist_globals / 失败行 item_index / 子图超时。

直调执行器（config 注入 _compiled_body fake），不建图——绕开 node_runner 的
流上下文，专注执行器语义本身（WF-P1-2 / WF-P1-5）。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_loop_batch_semantics.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from app.core.config import settings
from app.modules.workflow.service.node_executors import (
    execute_batch_processor_node,
    execute_loop_controller_node,
)


class _FakeBody:
    """体子图 fake：ainvoke 委托给定函数（返回 {"variables": ...}）或直接抛异常。"""

    def __init__(self, fn: Callable[[dict], dict[str, Any]] | Callable[[dict], Exception]):
        self._fn = fn

    async def ainvoke(self, state: dict) -> dict[str, Any]:
        result = self._fn(state)
        if isinstance(result, Exception):
            raise result
        return result


def _loop_config(**overrides: Any) -> dict[str, Any]:
    config = {
        "_compiled_body": _FakeBody(lambda state: {"variables": state["variables"]}),
        "list_variable": "list_variable",
        "item_variable": "loop_item",
        "output_variable": "loop_results",
    }
    config.update(overrides)
    return config


def _batch_config(**overrides: Any) -> dict[str, Any]:
    config = {
        "_compiled_body": _FakeBody(lambda state: {"variables": state["variables"]}),
        "list_variable": "list_variable",
        "item_variable": "batch_item",
        "output_variable": "batch_results",
    }
    config.update(overrides)
    return config


def _loop_variables() -> dict[str, Any]:
    return {"list_variable": [1, 2, 3], "x": "orig"}


class LoopCollectKeysTestCase(unittest.TestCase):
    def test_collect_keys_whitelist(self):
        """配置白名单后每轮只收集白名单键。"""

        def body(state: dict) -> dict:
            vs = state["variables"]
            vs["a"] = 1
            vs["b"] = 2
            vs["c"] = 3
            return {"variables": vs}

        result = asyncio.run(
            execute_loop_controller_node(
                _loop_variables(), _loop_config(_compiled_body=_FakeBody(body), collect_keys=["a"])
            )
        )
        for iter_output in result["loop_results"]:
            self.assertEqual(set(iter_output.keys()), {"a"})

    def test_no_collect_keys_keeps_full_snapshot_compat(self):
        """未配置 collect_keys：保持兼容行为（除循环临时变量外的全量快照）。"""
        result = asyncio.run(execute_loop_controller_node(_loop_variables(), _loop_config()))
        first = result["loop_results"][0]
        self.assertEqual(set(first.keys()), {"list_variable", "x"})
        self.assertNotIn("loop_item", first)
        self.assertNotIn("loop_item_index", first)


class LoopPersistGlobalsTestCase(unittest.TestCase):
    def test_persist_globals_merges_new_keys_only(self):
        """persist_globals：迭代期新增键并入返回值（排除循环临时变量）。"""

        def body(state: dict) -> dict:
            vs = state["variables"]
            vs["acc"] = vs.get("acc", 0) + 1
            vs["new_key"] = "new"
            return {"variables": vs}

        result = asyncio.run(
            execute_loop_controller_node(
                _loop_variables(), _loop_config(_compiled_body=_FakeBody(body), persist_globals=True)
            )
        )
        self.assertEqual(result["acc"], 3, "链式累积的最终值")
        self.assertEqual(result["new_key"], "new")
        self.assertNotIn("loop_item", result)
        self.assertNotIn("loop_item_index", result)

    def test_persist_globals_does_not_write_back_modified_existing_keys(self):
        """键差集语义：循环体改写既有变量不回写（防意外覆盖主图状态）。"""

        def body(state: dict) -> dict:
            vs = state["variables"]
            vs["x"] = "modified"  # 改写既有键
            vs["added"] = 1  # 新增键
            return {"variables": vs}

        result = asyncio.run(
            execute_loop_controller_node(
                _loop_variables(), _loop_config(_compiled_body=_FakeBody(body), persist_globals=True)
            )
        )
        self.assertNotIn("x", result, "既有键的改写不应回写")
        self.assertEqual(result["added"], 1)


class BatchSemanticsTestCase(unittest.TestCase):
    def test_collect_keys_whitelist(self):
        def body(state: dict) -> dict:
            vs = state["variables"]
            vs["a"] = vs["batch_item"]
            vs["b"] = "noise"
            return {"variables": vs}

        result = asyncio.run(
            execute_batch_processor_node(
                _loop_variables(), _batch_config(_compiled_body=_FakeBody(body), collect_keys=["a"])
            )
        )
        for iter_output in result["batch_results"]:
            self.assertEqual(set(iter_output.keys()), {"a"})

    def test_persist_globals_ignored_with_warning(self):
        recorded = []
        with patch(
            "app.modules.workflow.service.node_executors.logger.warning",
            side_effect=lambda msg, *a: recorded.append(msg % a if a else msg),
        ):
            result = asyncio.run(execute_batch_processor_node(_loop_variables(), _batch_config(persist_globals=True)))
        self.assertEqual(set(result.keys()), {"batch_results"}, "persist_globals 应被忽略（不并入全局键）")
        self.assertTrue(any("persist_globals" in r for r in recorded), f"应输出忽略告警: {recorded}")


class FailureRowShapeTestCase(unittest.TestCase):
    def test_loop_failure_rows_carry_item_index(self):
        """stop_on_error=False 时连续失败行都带 item_index，可定位失败项。"""

        def body(state: dict) -> dict:
            if state["variables"]["loop_item"] == 2:
                raise RuntimeError("boom-2")
            return {"variables": state["variables"]}

        result = asyncio.run(
            execute_loop_controller_node(
                _loop_variables(),
                _loop_config(_compiled_body=_FakeBody(body), stop_on_error=False),
            )
        )
        self.assertEqual(result["loop_results"][1], {"error": "boom-2", "item_index": 1})

    def test_batch_failure_rows_carry_item_index(self):
        def body(state: dict) -> dict:
            if state["variables"]["batch_item"] == 2:
                raise RuntimeError("boom-2")
            return {"variables": state["variables"]}

        result = asyncio.run(
            execute_batch_processor_node(_loop_variables(), _batch_config(_compiled_body=_FakeBody(body)))
        )
        failed = [r for r in result["batch_results"] if "error" in r]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0], {"error": "boom-2", "item_index": 1})


class SubgraphTimeoutTestCase(unittest.TestCase):
    def test_loop_timeout_with_node_config(self):
        """节点 timeoutSeconds 收紧：整轮迭代受 wait_for 约束并给出友好归因。"""

        def slow_body(state: dict) -> dict:
            raise AssertionError("不应执行到 body（在 sleep 中即被取消）")

        class _SlowBody:
            async def ainvoke(self, state: dict) -> dict[str, Any]:
                await asyncio.sleep(1)
                return {"variables": state["variables"]}

        with self.assertRaises(ValueError) as cm:
            asyncio.run(
                execute_loop_controller_node(
                    _loop_variables(),
                    _loop_config(_compiled_body=_SlowBody(), timeout_seconds=0.05),
                )
            )
        self.assertIn("循环体执行超时", str(cm.exception))

    def test_batch_timeout_with_node_config(self):
        class _SlowBody:
            async def ainvoke(self, state: dict) -> dict[str, Any]:
                await asyncio.sleep(1)
                return {"variables": state["variables"]}

        with self.assertRaises(ValueError) as cm:
            asyncio.run(
                execute_batch_processor_node(
                    _loop_variables(),
                    _batch_config(_compiled_body=_SlowBody(), timeout_seconds=0.05),
                )
            )
        self.assertIn("批处理体执行超时", str(cm.exception))

    def test_timeout_falls_back_to_default_settings(self):
        """未配置 timeout_seconds 时回落 WORKFLOW_SUBGRAPH_TIMEOUT。"""
        patcher = patch.object(settings, "WORKFLOW_SUBGRAPH_TIMEOUT", 0.05)
        patcher.start()
        try:
            with self.assertRaises(ValueError) as cm:
                asyncio.run(
                    execute_loop_controller_node(
                        _loop_variables(),
                        _loop_config(_compiled_body=_SlowBody2()),
                    )
                )
            self.assertIn("循环体执行超时", str(cm.exception))
        finally:
            patcher.stop()


class _SlowBody2:
    async def ainvoke(self, state: dict) -> dict[str, Any]:
        await asyncio.sleep(1)
        return {"variables": state["variables"]}


if __name__ == "__main__":
    unittest.main()
