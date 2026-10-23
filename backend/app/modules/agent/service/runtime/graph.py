"""自组小 StateGraph（设计 3.4.1，D7 不用弃用的 create_react_agent）。

图: START → call_model →(条件边)→ execute_tools → call_model；无 tool_calls → END。
- 条件边：含 tool_calls 且 tool_rounds < max_tool_rounds → execute_tools；
  含 tool_calls 但轮数耗尽 → 追加兜底 AIMessage → END；无 tool_calls → END。
- 计数权威表（评审 P0-1）：model_calls 在 call_model 执行时 +1（观测与预算）；
  tool_rounds 在进入工具执行节点时 +1（一轮多调用计 1 轮，预算拒绝轮仍计 1）。
- 编译不挂 checkpointer（D13：会话状态持久化在 agent_message，HITL 扩展期再引入）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

# add_messages reducer（langgraph 1.x 路径）
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.modules.agent.service.runtime.memory_service import (
    build_model_messages,
)
from app.modules.agent.service.runtime.model_wrapper import LoomChatModel
from app.modules.agent.service.runtime.run_service import (
    PendingToolCall,
    RunBudget,
    dispose_pending_tool_calls,
    fallback_reply,
)
from app.modules.agent.service.runtime.tool_executor import ToolExecutor

logger = logging.getLogger("agent.graph")


class AgentState(TypedDict):
    """运行态：messages 全量累积（裁剪只在 call_model 内进行，不回写）；双计数器。"""

    messages: Annotated[list[AnyMessage], add_messages]
    model_calls: int  # 模型调用次数（预算与观测）
    tool_rounds: int  # 已执行的工具迭代轮数（上限 = max_tool_rounds）


class GraphDeps:
    """图的运行时依赖集（run 发起时构造一次；单 run 实例纪律）。"""

    def __init__(
        self,
        *,
        model: LoomChatModel,
        tool_executor: ToolExecutor,
        budget: RunBudget,
        system_message: str,
        tool_schema_tokens: int,
        max_tool_rounds: int,
        pre_model_hooks: list | None = None,  # 产出型中间件（MemoryInjection 等，返回 state delta）
        apply_hooks: Callable | None = None,  # apply_pre_model_hooks
        guardrails_validator: Callable[[list], None] | None = None,  # 校验型（护栏完整性，对组装后 messages）
        should_cancel: Callable[[], bool] | None = None,
        should_stop_scheduling: Callable[[], bool] | None = None,  # 锁所有权校验（P5 注入）
        on_final: Callable[[AgentState], None] | None = None,
    ):
        self.model = model
        self.tool_executor = tool_executor
        self.budget = budget
        self.system_message = system_message
        self.tool_schema_tokens = tool_schema_tokens
        self.max_tool_rounds = max_tool_rounds
        self.pre_model_hooks = pre_model_hooks or []
        self.apply_hooks = apply_hooks
        self.guardrails_validator = guardrails_validator
        self.should_cancel = should_cancel or (lambda: False)
        self.should_stop_scheduling = should_stop_scheduling or (lambda: False)
        self.on_final = on_final


def _call_model(state: AgentState, deps: GraphDeps) -> dict:
    """模型调用节点：预算/取消/锁所有权检查 → 上下文组装 → LoomChatModel.invoke → 计数。"""
    messages = list(state.get("messages") or [])
    if not deps.budget.can_call_model():
        return {"messages": [fallback_reply(deps.budget.exhausted_reason)], "model_calls": 0}
    if deps.should_cancel() or deps.should_stop_scheduling():
        # 终止路径的兜底说明（真实终态由外层 run 线程标注 cancelled）
        return {"messages": [AIMessage(content="（本次运行已停止。）")], "model_calls": 0}

    # ① 产出型 pre_model 钩子（记忆注入 → injected_context，交由裁剪器按预算消费）
    probe_state = {"messages": messages}
    injected = ""
    if deps.apply_hooks is not None and deps.pre_model_hooks:
        delta = deps.apply_hooks(deps.pre_model_hooks, probe_state, None) or {}
        injected = delta.get("injected_context") or ""

    # ② 上下文组装（system 消息在此前置——护栏唯一注入点在 prompt_render.render）
    # 契约：state.messages 的最后一条即当前用户输入（run 发起时构造）
    assembled = build_model_messages(
        system_message=deps.system_message,
        tool_schema_tokens=deps.tool_schema_tokens,
        injected_context=injected,
        history=messages[:-1] if messages else [],
        current_input=str(messages[-1].content) if messages else "",
    )
    # ③ 校验型钩子：护栏完整性对「提交给模型的 messages」验证（fail-close）
    if deps.guardrails_validator is not None:
        deps.guardrails_validator(assembled)
    llm_result = deps.model.generate([assembled])  # LLMResult：message + llm_output.usage（预算 token 计数）
    response = llm_result.generations[0][0].message
    deps.budget.on_model_call((llm_result.llm_output or {}).get("usage"))
    # 无 reducer 通道为覆盖语义：返回全量（当前值 +1），不返回增量
    return {"messages": [response], "model_calls": int(state.get("model_calls") or 0) + 1}


def _execute_tools(state: AgentState, deps: GraphDeps) -> dict:
    """工具执行节点：进入即计 1 轮（评审 P0-1 递增时机）；顺序执行 + 超限同构处置。"""
    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    calls = list(getattr(last, "tool_calls", None) or [])
    deps.budget.on_tool_round(len(calls))

    outcomes = deps.tool_executor.execute_round(last)
    tool_messages = ToolExecutor.to_tool_messages(outcomes)

    # ⑥ 超限同构处置：预算触顶后同轮剩余调用未执行——补齐配对（execute_round 已含取消/
    # 预算内拒绝路径，此处兜底处理未产出结果的 call_id，保证结构完整）
    answered = {m.tool_call_id for m in tool_messages}
    pending = [
        PendingToolCall(call_id=c.get("id") or "", name=c.get("name") or "")
        for c in calls
        if (c.get("id") or "") not in answered
    ]
    if pending:
        extras = dispose_pending_tool_calls(
            pending,
            note="已达工具调用上限，未执行",
            on_result=lambda _cid, _content: None,
        )
        for item in extras:
            tool_messages.append(
                ToolMessage(
                    content="已达工具调用上限，未执行",
                    tool_call_id=item["toolCallId"],
                    name=item["toolName"],
                )
            )
    return {"messages": tool_messages, "tool_rounds": int(state.get("tool_rounds") or 0) + 1}


def _should_continue(state: AgentState, deps: GraphDeps) -> str:
    """条件边：含 tool_calls 且未达轮数上限 → tools；轮数耗尽 → budget_fallback（同构处置后收尾）；
    无 tool_calls → END。"""
    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        if deps.budget.can_execute_round():
            return "tools"
        return "budget_fallback"
    return END


def _budget_fallback(state: AgentState, deps: GraphDeps) -> dict:
    """轮数/预算耗尽收尾节点（设计 3.4.1 条件边 + 3.4.4 ⑥ 同构处置）：
    对最后一条 AI 的未执行 tool_calls 补齐配对 ToolMessage，再追加兜底 AIMessage——
    不留残缺配对进历史（3.4.5 原子单元规则）。"""
    from langchain_core.messages import ToolMessage

    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    additions: list[AnyMessage] = []
    for call in getattr(last, "tool_calls", None) or []:
        additions.append(
            ToolMessage(
                content="已达工具迭代轮数上限，未执行",
                tool_call_id=call.get("id") or "",
                name=call.get("name") or "",
            )
        )
    additions.append(fallback_reply("tool_rounds"))
    return {"messages": additions}


def build_agent_graph(deps: GraphDeps):
    """编译一次 run 的执行图（不挂 checkpointer，D13）。"""
    builder = StateGraph(AgentState)
    builder.add_node("call_model", lambda state: _call_model(state, deps))
    builder.add_node("execute_tools", lambda state: _execute_tools(state, deps))
    builder.add_node("budget_fallback", lambda state: _budget_fallback(state, deps))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        lambda state: _should_continue(state, deps),
        {"tools": "execute_tools", "budget_fallback": "budget_fallback", END: END},
    )
    builder.add_edge("execute_tools", "call_model")
    builder.add_edge("budget_fallback", END)
    return builder.compile()
