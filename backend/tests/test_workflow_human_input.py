"""人工审批节点中断挂起（P0-1 端到端守护）。

断言经 `create_node_runner` 包装的 `human_input` 节点在真实 LangGraph 图中首次
`interrupt()` 即挂起：`astream(stream_mode="updates")` 产出 `__interrupt__` 事件，
而**不是**被重试逻辑包装成 `NodeExecutionError`（那会使实例永远无法进入 paused）。

对照的上层处理逻辑：`app/modules/workflow/tasks/workflow_tasks.py` 中
`if node_id == "__interrupt__":` → 写 paused 终态 + 推送事件。
"""

from __future__ import annotations

import asyncio
import unittest

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

# 显式导入以完成节点执行器注册（本测试直接构造图，不经过 compile_graph 的延迟导入）
import app.modules.workflow.service.workflow_service  # noqa: F401
from app.modules.workflow.service.compiler import WorkflowCompiler, WorkflowState


class HumanInputInterruptTestCase(unittest.TestCase):
    """human_input 经节点包装器后仍能正常挂起。"""

    def _build_graph(self, attempts: int):
        runner = WorkflowCompiler.create_node_runner(
            "hi_1",
            "human_input",
            {
                "retry_max_attempts": attempts,
                "retry_backoff_base": 0.0,
                "message": "请审批",
                "output_variable": "approval_result",
            },
        )
        builder = StateGraph(WorkflowState)
        builder.add_node("hi_1", runner)
        builder.add_edge(START, "hi_1")
        builder.add_edge("hi_1", END)
        return builder.compile(checkpointer=InMemorySaver())

    async def _stream_events(self, attempts: int) -> list[dict]:
        graph = self._build_graph(attempts)
        config = {"configurable": {"thread_id": f"t{attempts}"}}
        return [
            event
            async for event in graph.astream(
                {"variables": {"a": 1}, "current_node": ""},
                config=config,
                stream_mode="updates",
            )
        ]

    def _assert_interrupted(self, attempts: int) -> None:
        events = asyncio.run(self._stream_events(attempts))
        interrupt_events = [e for e in events if "__interrupt__" in e]

        self.assertTrue(
            interrupt_events,
            f"未产出 __interrupt__ 事件（attempts={attempts}），实际事件键：{[list(e) for e in events]}",
        )
        interrupts = interrupt_events[0]["__interrupt__"]
        self.assertTrue(interrupts, "中断事件载荷为空")
        self.assertEqual(interrupts[0].value.get("message"), "请审批")
        self.assertEqual(interrupts[0].value.get("output_variable"), "approval_result")

    def test_human_input_pauses_graph_by_default(self):
        """默认重试配置（1 次）下首次 interrupt 即挂起。"""
        self._assert_interrupted(attempts=1)

    def test_human_input_not_retried_when_retry_configured(self):
        """显式配置 3 次重试时，中断信号也不得被重试消耗掉。"""
        self._assert_interrupted(attempts=3)


if __name__ == "__main__":
    unittest.main()
