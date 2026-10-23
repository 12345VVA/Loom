"""RunService：三层预算 + 终态机 + 超限/终止处置（设计 3.4.4）。

P3 本文件承载纯逻辑（RunBudget / 兜底回复 / 同构处置）；invoke/stream 的会话编排与
SSE 事件队列在 P5 落地（依赖发布快照与会话服务）。

预算触发一致性：任一运行层预算耗尽 → 注入明示原因的兜底回复 → 终态 completed
（受控结束非失败；error 备注记录触发项）；timed_out 仅总时限、failed 仅致命错误。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage

from app.modules.agent.model.agent import (
    AGENT_RUN_COMPLETED,
    AGENT_RUN_TIMED_OUT,
)
from app.modules.agent.service.runtime.memory_service import AGENT_RUN_TOKEN_BUDGET

# 预算常量（设计 3.4.4 三层预算表；模块级便于测试覆写）
MODEL_CALLS_MULTIPLIER = 1  # model_calls 上限 = max_tool_rounds + 1（每轮工具后一次模型调用 + 收尾）
TOOL_CALLS_MULTIPLIER = 4  # tool_calls 上限 = 4 × max_tool_rounds（防异常硬限制，非完成保证）

_BUDGET_FALLBACKS = {
    "tool_rounds": "已达到本智能体配置的工具迭代轮数上限，以下为基于当前信息的回答。",
    "model_calls": "已达到本次运行的模型调用预算上限，以下为基于当前信息的回答。",
    "tool_calls": "已达到本次运行的工具调用次数上限，以下为基于当前信息的回答。",
    "run_tokens": "已达到本次运行的 token 预算上限，以下为基于当前信息的回答。",
}


class RunBudget:
    """整次运行预算（第三层）：model_calls / tool_rounds / tool_calls / 累计 token。"""

    def __init__(self, max_tool_rounds: int, run_token_budget: int = AGENT_RUN_TOKEN_BUDGET):
        self.max_model_calls = max_tool_rounds + MODEL_CALLS_MULTIPLIER
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_calls = max_tool_rounds * TOOL_CALLS_MULTIPLIER
        self.run_token_budget = run_token_budget
        self.model_calls = 0
        self.tool_rounds = 0
        self.tool_calls = 0
        self.total_tokens = 0
        self.exhausted_reason: str | None = None

    # --- 判定（调用前）---

    def can_call_model(self) -> bool:
        if self.model_calls >= self.max_model_calls:
            return self._mark("model_calls")
        if self.total_tokens >= self.run_token_budget:
            return self._mark("run_tokens")
        return True

    def can_execute_round(self) -> bool:
        if self.tool_rounds >= self.max_tool_rounds:
            return self._mark("tool_rounds")
        return True

    # --- 累计（调用后）---

    def on_model_call(self, usage: dict | None = None) -> None:
        self.model_calls += 1
        if usage:
            self.total_tokens += int(usage.get("totalTokens") or usage.get("total_tokens") or 0)
        if self.total_tokens >= self.run_token_budget:
            self._mark("run_tokens")

    def on_tool_round(self, tool_call_count: int) -> None:
        """进入工具执行节点时递增一轮（一轮含多个工具调用计 1 轮——计数权威表）。"""
        self.tool_rounds += 1
        self.tool_calls += tool_call_count
        if self.tool_calls >= self.max_tool_calls:
            self._mark("tool_calls")

    def _mark(self, reason: str) -> bool:
        if self.exhausted_reason is None:
            self.exhausted_reason = reason
        return False


@dataclass
class PendingToolCall:
    """一轮中尚未获得结果回填的 tool_call（超限/终止同构处置的工作单元）。"""

    call_id: str
    name: str


def fallback_reply(reason: str | None) -> AIMessage:
    """预算耗尽的兜底回复（明示原因；终态 completed 非 failed）。"""
    text = _BUDGET_FALLBACKS.get(reason or "", "本次运行已按预算约束收尾。")
    return AIMessage(content=f"（{text}）")


def dispose_pending_tool_calls(
    pending: list[PendingToolCall],
    *,
    note: str,
    on_result: Callable[[str, str], None],
) -> list[dict]:
    """超限/终止的同构处置（设计 3.4.4 ⑥⑦）：保证每个 tool_call_id 都有配对结果。

    pending：本轮未执行的 tool_calls（预算中途触顶或 cancelled/timed_out/failed）；
    on_result(call_id, content)：调用方回填 ToolMessage / 落消息库。
    返回处置记录（观测用）。
    """
    disposed = []
    for item in pending:
        content = f"{note}（tool_call_id={item.call_id}）"
        on_result(item.call_id, content)
        disposed.append({"toolCallId": item.call_id, "toolName": item.name, "disposed": True})
    return disposed


class RunDeadline:
    """run 总时限（timeout_seconds）观测器。"""

    def __init__(self, timeout_seconds: int):
        self._started = time.monotonic()
        self._timeout = timeout_seconds

    def remaining(self) -> float:
        return max(0.0, self._timeout - (time.monotonic() - self._started))

    def expired(self) -> bool:
        return self.remaining() <= 0

    def per_request_timeout(self, profile_timeout: int) -> int:
        """单轮模型请求超时 = min(run 剩余时限, profile.timeout)（取消三层语义之三）。"""
        return max(1, min(int(self.remaining()) + 1, profile_timeout))


_ = field  # noqa: B018 —— dataclass 导入占位（PendingToolCall 扩展用）
_ = AGENT_RUN_COMPLETED
_ = AGENT_RUN_TIMED_OUT
