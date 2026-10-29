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
import time
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

# add_messages reducer（langgraph 1.x 路径）
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.modules.agent.service.runtime.budget import (
    PendingToolCall,
    RunBudget,
    dispose_pending_tool_calls,
    fallback_reply,
)
from app.modules.agent.service.runtime.memory_service import (
    AGENT_CONTEXT_TOKEN_BUDGET,
    build_model_messages,
)
from app.modules.agent.service.runtime.model_wrapper import LoomChatModel
from app.modules.agent.service.runtime.timing import timed
from app.modules.agent.service.runtime.tool_executor import ToolExecutor

logger = logging.getLogger("agent.graph")


class ApprovalSuspension(Exception):
    """E4 整组预检命中：本轮含需审批调用（整轮零执行，二批 3.5）。

    携带挂起轮的 AIMessage（tool_calls 为组重建锚点）；由 run_service 捕获后落审批行、
    置 trace=waiting_approval、emit approval_required 并结束本次执行线程。
    """

    def __init__(self, ai_message: AIMessage):
        super().__init__(f"本轮含需审批调用（{len(ai_message.tool_calls or [])} 个调用整组挂起）")
        self.ai_message = ai_message


def _approval_calls(ai_message: AIMessage) -> list[dict]:
    """整组预检：任一 call 指向需审批工具（当前注册 level 实时判定，D14）→ 整组挂起。"""
    from app.modules.agent.service.approval_service import approval_required_for

    return [c for c in (ai_message.tool_calls or []) if approval_required_for(c.get("name") or "")]


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
        context_token_budget: int | None = None,  # E15 动态输入预算（None = 常数下限）
        stream_answer: bool = False,  # E1：最终答案候选轮 token 流式（仅 SSE 会话启用）
        pre_model_hooks: list | None = None,  # 产出型中间件（MemoryInjection 等，返回 state delta）
        apply_hooks: Callable | None = None,  # apply_pre_model_hooks
        guardrails_validator: Callable[[list], None] = None,  # type: ignore[assignment] —— 校验型（护栏完整性，对组装后 messages）
        run_ctx: Any = None,  # 五钩子 RunContext（pre_model 钩子消费者；None = 测试桩直构）
        on_event: Callable[[str, dict], None] | None = None,  # 受控事件队列出口（SSE，P5）
        should_cancel: Callable[[], bool] | None = None,
        should_stop_scheduling: Callable[[], bool] | None = None,  # 锁所有权校验（P5 注入）
        on_final: Callable[[AgentState], None] | None = None,
        trace_token: str | None = None,  # 耗时打点关联（agent.timing 日志字段）
        heartbeat: Callable[[], None] | None = None,  # 轮间心跳（复核问题③）：假死 sweep 的「无活动」判据
    ):
        self.trace_token = trace_token
        self.heartbeat = heartbeat
        self.model = model
        self.tool_executor = tool_executor
        self.budget = budget
        self.system_message = system_message
        self.tool_schema_tokens = tool_schema_tokens
        self.max_tool_rounds = max_tool_rounds
        self.context_token_budget = context_token_budget or AGENT_CONTEXT_TOKEN_BUDGET
        self.stream_answer = stream_answer
        self.pre_model_hooks = pre_model_hooks or []
        self.apply_hooks = apply_hooks
        self.run_ctx = run_ctx
        self.guardrails_validator = guardrails_validator
        self.on_event = on_event
        self.should_cancel = should_cancel or (lambda: False)
        self.should_stop_scheduling = should_stop_scheduling or (lambda: False)
        self.on_final = on_final


def _normalize_usage(usage: dict | None) -> dict:
    """usage 键归一为 snake_case 三键（ai adapter 产出为 camelCase——前端 token 统计
    曾因读 prompt_tokens 恒 0；预算/事件/落库统一走本形态）。"""
    if not usage:
        return {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or usage.get("promptTokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or usage.get("completionTokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or usage.get("totalTokens") or 0),
    }


def _call_model(state: AgentState, deps: GraphDeps) -> dict:
    """模型调用节点：预算/取消/锁所有权检查 → 上下文组装 → LoomChatModel.invoke → 计数。"""
    messages = list(state.get("messages") or [])
    if not deps.budget.can_call_model():
        return {"messages": [fallback_reply(deps.budget.exhausted_reason)], "model_calls": 0}
    if deps.should_cancel() or deps.should_stop_scheduling():
        # 终止路径的兜底说明（真实终态由外层 run 线程标注 cancelled）
        return {"messages": [AIMessage(content="（本次运行已停止。）")], "model_calls": 0}

    trace_token = deps.trace_token
    # ① 产出型 pre_model 钩子（记忆注入 → injected_context，交由裁剪器按预算消费）
    probe_state = {"messages": messages}
    injected = ""
    if deps.apply_hooks is not None and deps.pre_model_hooks:
        delta = deps.apply_hooks(deps.pre_model_hooks, probe_state, deps.run_ctx) or {}
        injected = delta.get("injected_context") or ""

    # ② 上下文组装（system 消息在此前置——护栏唯一注入点在 prompt_render.render）
    # 契约：首轮 state.messages 的最后一条即当前用户输入；工具循环轮尾部是工具结果段，
    # 整体留在 history 原子单元（协议：tool_calls 后必须紧跟 tool 角色，不得展平为 user）
    with timed("llm.assemble", trace_token=trace_token):
        if messages and isinstance(messages[-1], ToolMessage):
            current_input = None  # 工具循环继续轮：无新用户输入
            history = messages
        else:
            # 当前输入 content 保真透传（str | 多模态数组——str() 化会把图片 parts 变成字符串污染）
            current_input = messages[-1].content if messages else ""
            history = messages[:-1] if messages else []
        assembled = build_model_messages(
            system_message=deps.system_message,
            tool_schema_tokens=deps.tool_schema_tokens,
            injected_context=injected,
            history=history,
            current_input=current_input,
            token_budget=deps.context_token_budget,  # E15：动态输入预算（链最小窗口 − 输出上限，下限兜底）
        )
        # ③ 校验型钩子：护栏完整性对「提交给模型的 messages」验证（fail-close）
        if deps.guardrails_validator is not None:
            deps.guardrails_validator(assembled)
    if deps.on_event is not None:
        deps.on_event("model_started", {"modelCalls": int(state.get("model_calls") or 0) + 1})
    round_started = time.perf_counter()
    with timed(
        "llm.round",
        level=logging.INFO,
        slow="model",
        message="agent LLM 轮次耗时",
        trace_token=trace_token,
    ) as bag:
        bag["round"] = int(state.get("model_calls") or 0) + 1
        bag["streaming"] = bool(deps.stream_answer)
        bag["profile"] = getattr(deps.model, "model_profile_code", "")
        if deps.stream_answer and deps.on_event is not None:
            response, raw_usage = _call_model_streaming(deps, assembled)
        else:
            llm_result = deps.model.generate_raw(
                assembled
            )  # ChatResult 直取（langchain generate 包装不透传 llm_output.usage）
            generations = llm_result.generations
            first = generations[0][0] if isinstance(generations[0], list) else generations[0]
            response = first.message
            raw_usage = (llm_result.llm_output or {}).get("usage") or {}
        usage = _normalize_usage(raw_usage)
        bag.update(prompt_tokens=usage.get("prompt_tokens"), total_tokens=usage.get("total_tokens"))
    deps.budget.on_model_call(usage)
    if deps.heartbeat is not None:
        deps.heartbeat()  # 模型响应完成即活动——BaseEntity 无 onupdate，updated_at 不会自动刷新
    if deps.on_event is not None:
        deps.on_event(
            "model_finished",
            {
                "hasToolCalls": bool(getattr(response, "tool_calls", None)),
                "usage": usage,
                "latencyMs": int((time.perf_counter() - round_started) * 1000),
            },
        )
    # 无 reducer 通道为覆盖语义：返回全量（当前值 +1），不返回增量
    return {"messages": [response], "model_calls": int(state.get("model_calls") or 0) + 1}


def _call_model_streaming(deps: GraphDeps, assembled) -> tuple[AIMessage, dict]:
    """E1 流式最终答案候选轮：answer_delta 实时下发（generation_id 分桶，seq 单调）；
    判定为工具决策响应（聚合 toolCalls 非空）→ answer_reset + **服务端同步撤销**
    （AIMessage 剔除临时文本仅保留 tool_calls 结构——被 reset 的内容不进入 agent_message、
    不进入后续上下文构建、不进入 trace 权威答案，设计 3.1 / D22 / A35）。"""
    generation_id = uuid.uuid4().hex
    seq = 0

    def on_delta(text: str) -> None:
        nonlocal seq
        seq += 1
        deps.on_event("answer_delta", {"generationId": generation_id, "delta": text, "seq": seq})

    result = deps.model.generate_streaming(assembled, on_delta)  # 平铺 list[BaseMessage]（非 generate 的 batch 语义）
    response = result.generations[0].message  # ChatResult 单层（区别于 generate 的 LLMResult 两层）
    usage = (result.llm_output or {}).get("usage") or {}
    if getattr(response, "tool_calls", None):
        deps.on_event("answer_reset", {"generationId": generation_id, "upToSeq": seq})
        # 服务端同步撤销：临时文本不入 state（messages 通道）——终局 ToolMessage/后续上下文/
        # trace 权威答案都不会再见到它；前端草稿区由 answer_reset 清除
        response = AIMessage(content="", tool_calls=response.tool_calls, additional_kwargs=response.additional_kwargs)
    else:
        deps.on_event("answer_done", {"generationId": generation_id, "seq": seq})
    return response, usage


def _execute_tools(state: AgentState, deps: GraphDeps) -> dict:
    """工具执行节点：进入即计 1 轮（评审 P0-1 递增时机）；顺序执行 + 超限同构处置。

    E4 整组预检（先于计数，工具链路专题 P2-1 勘误）：本轮任一调用需审批 →
    raise ApprovalSuspension（整轮零执行，挂起轮 tool_round 不累加——恢复侧
    budget.tool_rounds = 0 依赖的正是该语义）。
    """
    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    calls = list(getattr(last, "tool_calls", None) or [])
    if last is not None and _approval_calls(last):
        raise ApprovalSuspension(last)
    deps.budget.on_tool_round(len(calls))

    with timed("tool.round", trace_token=deps.trace_token, tool_count=len(calls)):
        outcomes = deps.tool_executor.execute_round(last)
    tool_messages = ToolExecutor.to_tool_messages(outcomes)
    for outcome in outcomes:
        if deps.on_event is not None:
            deps.on_event(
                "tool_finished" if outcome.skipped_reason is None else "tool_skipped",
                {"toolCallId": outcome.call_id, "toolName": outcome.name, "success": outcome.success},
            )

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
    if deps.heartbeat is not None:
        deps.heartbeat()  # 工具轮完成即活动（多轮长 run 的主要心跳源）
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
