"""ToolExecutor（设计 3.4.1 execute_tools）：顺序执行 + 双判定 + 参数校验 + 计时落库。

一轮多调用成功语义：允许部分成功——单个工具失败不中止本轮，错误信息作为该工具的
ToolMessage 回填模型（D12 错误归一）。顺序执行前提：工具共享 ctx.db（Session 不跨线程）。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from app.core.config import settings
from app.modules.agent.model.agent import AGENT_MESSAGE_ROLES
from app.modules.agent.service.runtime.memory_service import truncate_tool_result
from app.modules.agent.service.runtime.middleware import ToolDenied, apply_wrap_tool
from app.modules.agent.service.runtime.timing import logger as timing_logger
from app.modules.agent.service.tool_registry import (
    assert_execution_allowed,
    get_tool,
    is_contract_compatible,
)

logger = logging.getLogger("agent.tool_executor")

# 契约不兼容的固定提示（fail-close 回填文案，设计 3.3）
CONTRACT_CHANGED_MESSAGE = "工具契约已变更，当前快照无法调用该工具，需重新发布智能体"


@dataclass
class ToolCallOutcome:
    """单个工具调用的执行结果（观测/落库/回填三消费）。"""

    call_id: str
    name: str
    content: str
    success: bool
    duration_ms: int
    skipped_reason: str | None = None  # contract_incompatible / denied / budget_exhausted / cancelled


class ToolExecutor:
    """一轮工具调用的顺序执行器（构造于 run 发起时，绑定快照工具面与执行上下文）。

    snapshot_tools: {tool_name: {"level": str, "parameters": dict}}——发布快照冻结的工具调用契约；
    context: ToolContext（db + 身份，执行流内同步使用）；
    should_cancel: Callable[[], bool]——每步前取消检查（取消三层语义之二：不再发起新调用）。
    """

    def __init__(
        self,
        *,
        snapshot_tools: dict[str, dict],
        bound_names: set[str],
        context: Any,  # ToolContext
        middlewares: list | None = None,
        should_cancel: Callable[[], bool] | None = None,
        log_tool_call: Callable[..., None] | None = None,  # trace_service 写 tool_call_log
        on_event: Callable[[str, dict], None] | None = None,  # 工具开始事件（结束事件由图层统一发）
    ):
        self.snapshot_tools = snapshot_tools
        self.bound_names = bound_names
        self.context = context
        self.middlewares = middlewares or []
        self.should_cancel = should_cancel or (lambda: False)
        self.log_tool_call = log_tool_call
        self.on_event = on_event

    def execute_round(self, ai_message: AIMessage) -> list[ToolCallOutcome]:
        """执行一轮全部 tool_calls（顺序）；返回逐个结果（含被拒/未执行项）。"""
        outcomes: list[ToolCallOutcome] = []
        for call in ai_message.tool_calls or []:
            call_id = call.get("id") or ""
            name = call.get("name") or ""
            args = call.get("args") or {}
            if self.should_cancel():
                outcomes.append(self._refuse(call_id, name, "已取消，未执行", "cancelled"))
                continue
            if self.on_event is not None:
                self.on_event("tool_started", {"toolCallId": call_id, "toolName": name})
            outcomes.append(self._execute_single(call_id, name, args))
        return outcomes

    # --- 单工具执行链（设计 3.3 两套判定 → 中间件 → 参数校验 → 执行 → 计时）---

    def execute_one(self, call_id: str, name: str, args: dict) -> ToolCallOutcome:
        """公开的单工具执行接口（架构审查 P1-1）：E4 恢复轮等外部执行链统一入口，
        完整走 _precheck 校验链；_execute_single 保留为内部实现名。"""
        return self._execute_single(call_id, name, args)

    def _execute_single(self, call_id: str, name: str, args: dict) -> ToolCallOutcome:
        started = time.monotonic()
        # E3：写工具经 ctx.audit_target_ref 上报目标引用——执行前清除防上一工具残留污染
        self.context.audit_target_ref = None
        try:
            tool, validated_args = self._precheck(call_id, name, args)
        except ToolCallRefused as refused:
            outcome = self._refuse(call_id, name, refused.message, refused.reason)
            self._write_log(outcome, args, started)
            return outcome

        try:
            result = tool.func(validated_args, self.context)
            outcome = ToolCallOutcome(
                call_id=call_id,
                name=name,
                content=result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                success=True,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except ToolDenied as exc:
            outcome = ToolCallOutcome(
                call_id=call_id,
                name=name,
                content=f"工具调用被拒绝：{exc}",
                success=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                skipped_reason="denied",
            )
        except (ValidationError, ValueError) as exc:
            outcome = ToolCallOutcome(
                call_id=call_id,
                name=name,
                content=f"工具参数校验失败：{exc}",
                success=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                skipped_reason="invalid_args",
            )
        except HTTPException as exc:
            outcome = ToolCallOutcome(
                call_id=call_id,
                name=name,
                content=f"工具执行失败：{exc.detail}",
                success=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                skipped_reason="http_error",
            )
        except Exception as exc:  # noqa: BLE001 —— D12 错误归一：失败回填由模型决定后续
            logger.exception("工具 %s 执行异常", name)
            outcome = ToolCallOutcome(
                call_id=call_id,
                name=name,
                content=f"工具执行异常：{exc}",
                success=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                skipped_reason="error",
            )
        self._write_log(outcome, args, started)
        return outcome

    def _precheck(self, call_id: str, name: str, args: dict):
        """执行前三重校验（3.3）：契约兼容 fail-close → 执行安全实时判定 → 参数校验。"""
        snapshot_entry = self.snapshot_tools.get(name)
        if snapshot_entry is None:
            raise ToolCallRefused(f"工具 {name} 未绑定到当前智能体快照", "not_bound")
        tool = get_tool(name)
        if tool is None:
            raise ToolCallRefused(CONTRACT_CHANGED_MESSAGE, "contract_incompatible")
        # 契约兼容性（快照 schema vs 当前注册 schema；不兼容 fail-close）
        if not is_contract_compatible(snapshot_entry.get("parameters") or {}, tool.parameters):
            raise ToolCallRefused(CONTRACT_CHANGED_MESSAGE, "contract_incompatible")
        # 执行安全性（实时：绑定/允许列表/level 升级/资源层启停）
        try:
            assert_execution_allowed(
                name,
                snapshot_level=snapshot_entry.get("level"),
                bound_tool_names=self.bound_names,
                session=self.context.db,
            )
        except HTTPException as exc:
            raise ToolCallRefused(str(exc.detail), "denied") from exc
        # 中间件 wrap_tool 链（拒绝链）
        try:
            args = apply_wrap_tool(self.middlewares, name, args, self.context)
        except ToolDenied as exc:
            raise ToolCallRefused(f"工具调用被拒绝：{exc}", "denied") from exc
        # 参数校验（当前 args_model——快照兼容但模型可能有新增可选字段）
        try:
            return tool, tool.args_model.model_validate(args)
        except ValidationError as exc:
            raise ToolCallRefused(f"工具参数校验失败：{exc}", "invalid_args") from exc

    def _refuse(self, call_id: str, name: str, message: str, reason: str) -> ToolCallOutcome:
        return ToolCallOutcome(
            call_id=call_id, name=name, content=message, success=False, duration_ms=0, skipped_reason=reason
        )

    def _write_log(self, outcome: ToolCallOutcome, args: dict, started: float) -> None:
        """tool_call_log 落库（观测二级；终态后残留工具仍可写自己的日志——独立生命周期）。"""
        if self.log_tool_call is None:
            return
        try:
            self.log_tool_call(
                tool_name=outcome.name,
                args_summary=json.dumps(args, ensure_ascii=False, default=str)[:500],
                result_summary=truncate_tool_result(outcome.content),
                target_ref=getattr(self.context, "audit_target_ref", None),  # E3 写操作目标审计
                duration_ms=outcome.duration_ms or int((time.monotonic() - started) * 1000),
                success=outcome.success if outcome.skipped_reason != "cancelled" else None,
                error=outcome.content if not outcome.success else None,
            )
        except Exception:  # noqa: BLE001 —— 日志失败不影响执行流
            logger.exception("tool_call_log 落库失败")

        # 慢调用告警（WARN-only；逐条明细以 AgentToolCallLog 为准，不双写 INFO）
        duration_ms = outcome.duration_ms or int((time.monotonic() - started) * 1000)
        threshold = int(getattr(settings, "AGENT_TIMING_SLOW_TOOL_MS", 0) or 0)
        if threshold and duration_ms >= threshold:
            timing_logger.warning(
                "工具慢调用",
                extra={
                    "phase": "tool.call",
                    "duration_ms": duration_ms,
                    "status": "ok" if outcome.success else "error",
                    "tool_name": outcome.name,
                    "tool_success": outcome.success,
                    "trace_id": self.context.trace_id,
                },
            )

    # --- 结果回填（ToolMessage）---

    @staticmethod
    def to_tool_messages(outcomes: list[ToolCallOutcome]) -> list[ToolMessage]:
        messages = []
        for outcome in outcomes:
            messages.append(
                ToolMessage(
                    content=truncate_tool_result(outcome.content, limit=4000),
                    tool_call_id=outcome.call_id,
                    name=outcome.name,
                )
            )
        return messages


class ToolCallRefused(Exception):
    """执行前校验拒绝（携带归类原因）。"""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.message = message
        self.reason = reason


_ = AGENT_MESSAGE_ROLES  # noqa: B018 —— 角色常量引用保留（消息落库校验用，P5 消费）
