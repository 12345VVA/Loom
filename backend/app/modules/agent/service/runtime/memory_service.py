"""上下文裁剪器（设计 3.4.5，需求 4.4）：持久化历史 ≠ 模型上下文。

硬规则：
- 原子单元不可分割：assistant.tool_calls 与其对应 tool 结果消息整体保留或整体剔除；
- 预算覆盖全部输入（护栏/system + 工具 schema + 注入上下文 + 历史 + 当前输入），
  分配采用优先级预留模型（必需项 → 当前输入完整 → 注入截断 → 历史拿剩余）；
- 当前输入超限显式报错（不静默截断——与资产 Composer 同哲学）；
- 工具结果三层截断（A4 修正注释——原「完整结果仅存 agent_message 与 tool_call_log」失实）：
  state 回填截 4000 字（agent_message 即此形态，>4000 字不留全量）、tool_call_log 摘要 200 字、
  历史注入 200 字——全量仅存在于执行瞬间。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

# 模块常量（设计 3.4.4 三层预算之二；二期接模型上下文上限元数据动态化）。
# 2026-10-28 调参（6000/30000 → 16000/60000）：6000 是「无图、工具返回几十字」时代的
# 保守初值，被附件多模态（图片 800 token/张）、会话记忆注入与长描述列表工具
# （单条结果 ~2500 字）逐步压穿——工具结果在组装层被截断导致模型读不全（真机走查实锤）。
# 24000 为「现有渠道窗口配置（32k）− 输出上限」下可设的最大安全值；注意 estimate_tokens
# 对中文高估 ~3 倍（2500 字估 5000，真实 ~1500）——常数是估算口径，有效容量约为字面 1/3
# （真机实测：16000 下 2500 字工具结果仍被剩余预算截断）；E15 公式对小窗口渠道
# 自动收紧（min(常数, 链窗口−输出)），上限放宽不引入爆窗风险。两常数须联动：
# 工具循环两轮的输入即可顶到 run 上限，单次上限翻倍则累计护栏同步翻倍。
AGENT_CONTEXT_TOKEN_BUDGET = 24000  # 单次输入上下文预算
AGENT_RUN_TOKEN_BUDGET = 80000  # 整次运行累计 token 预算
TOOL_RESULT_INJECT_LIMIT = 200  # （保留兼容引用）工具结果摘要截断字数
TOOL_RESULT_HISTORY_LIMIT = 4000  # 历史组装时工具结果截断字数（对齐 state 回填口径，2026-10-28 由 200 修正）

# 保底：即使超预算也至少保留的最近原子单元数（超长按单条截断处理而非丢弃）
MIN_KEEP_UNITS = 2


class ContextBudgetError(Exception):
    """当前输入超过有效输入预算（显式失败，不静默截断）。"""


def estimate_tokens(text: str) -> int:
    """粗估 token：ASCII 0.75/字符、非 ASCII 2/字符（外部工程先例，仅用于预算裁剪）。"""
    if not text:
        return 0
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    return int(ascii_count * 0.75) + (len(text) - ascii_count) * 2


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, list):
        # 多模态 Content Parts：只拼文本部件——base64 图片数据严禁进入（token 估算会爆炸）
        return "\n".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


# 图片部件 token 估算常数（base64 不入估算；对齐常见视觉模型单图量级）
IMAGE_PART_TOKEN_ESTIMATE = 800


def _content_part_tokens(content: Any) -> int:
    """多模态 content 的 token 估算：text 部件正常估算，image 部件按常数。"""
    if not isinstance(content, list):
        return estimate_tokens(str(content))
    total = 0
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            total += IMAGE_PART_TOKEN_ESTIMATE
        elif isinstance(part, dict):
            total += estimate_tokens(str(part.get("text") or ""))
        else:
            total += estimate_tokens(str(part))
    return total


def _message_tokens(message: BaseMessage) -> int:
    extra = ""
    if isinstance(message, AIMessage) and message.tool_calls:
        extra = str(message.tool_calls)
    if isinstance(message, ToolMessage):
        extra = message.tool_call_id or ""
    content_tokens = (
        _content_part_tokens(message.content)
        if isinstance(message.content, list)
        else estimate_tokens(_message_text(message))
    )
    return content_tokens + estimate_tokens(extra)


def truncate_tool_result(result: str, limit: int = TOOL_RESULT_INJECT_LIMIT) -> str:
    """工具结果注入历史前的截断（完整结果已存 agent_message / tool_call_log）。"""
    if len(result) <= limit:
        return result
    return result[:limit] + "…（已截断，完整结果见调用日志）"


def _atomic_units(history: list[BaseMessage]) -> list[list[BaseMessage]]:
    """把历史切分为原子单元：assistant(tool_calls) + 其后的 tool 结果消息为一个单元。

    顺序假设：tool 结果紧跟其 assistant 消息（langgraph 工具循环的天然顺序）。
    """
    units: list[list[BaseMessage]] = []
    pending: list[BaseMessage] = []
    for message in history:
        if isinstance(message, ToolMessage):
            if not pending:
                # 孤儿 tool 结果（前无 assistant.tool_calls）——单独成单元（3.4.5 兜底不再产生此形态）
                units.append([message])
            else:
                pending.append(message)
            continue
        if pending:
            units.append(pending)
            pending = []
        if isinstance(message, AIMessage) and message.tool_calls:
            pending = [message]
        else:
            units.append([message])
    if pending:
        units.append(pending)
    return units


def _truncate_single_unit(unit: list[BaseMessage], budget: int) -> list[BaseMessage] | None:
    """保底场景的单条截断：工具结果内容截断后尝试放回。"""
    kept: list[BaseMessage] = []
    used = 0
    for message in unit:
        tokens = _message_tokens(message)
        if tokens <= budget - used:
            kept.append(message)
            used += tokens
            continue
        if isinstance(message, ToolMessage):
            text = _message_text(message)
            # 按剩余预算近似截字符（非 ASCII 下更保守，允许少量超支由外层校验兜底）
            keep_chars = max(0, (budget - used) * 2)
            if keep_chars > 20:
                truncated = ToolMessage(
                    content=truncate_tool_result(text, keep_chars),
                    tool_call_id=message.tool_call_id or "",
                    name=message.name,
                )
                kept.append(truncated)
                used += _message_tokens(kept[-1])
                continue
        return None  # 无法塞下 → 放弃该单元
    return kept


def build_model_messages(
    *,
    system_message: str,
    tool_schema_tokens: int,
    injected_context: str,
    history: list[BaseMessage],
    current_input: str | None,
    token_budget: int = AGENT_CONTEXT_TOKEN_BUDGET,
) -> list[BaseMessage]:
    """按优先级预留模型组装提交给模型的 messages 序列。

    ① 必需项（护栏/system + 工具 schema）→ ② 当前输入必须完整 → ③ 注入上下文按优先级截断
    → ④ 历史拿剩余预算按完整原子单元裁剪（保底最近 2 个单元超长单条截断）。
    工具结果注入历史前截 200 字（3.4.5；完整结果仅存 agent_message 与 tool_call_log）。
    system+schema 超预算属配置错误直接报错；当前输入超限显式报错（不静默截断）。
    current_input=None 表示工具循环继续轮（无新用户输入；尾部工具结果段整体留在 history
    原子单元内——openai 协议要求 tool_calls 后紧跟 tool 角色，不得展平为 user）。
    """
    from langchain_core.messages import SystemMessage

    system_tokens = estimate_tokens(system_message)
    if system_tokens + tool_schema_tokens >= token_budget:
        raise ContextBudgetError(
            f"系统提示词与工具 schema（约 {system_tokens + tool_schema_tokens} tokens）超出输入预算 {token_budget}"
        )

    remaining = token_budget - system_tokens - tool_schema_tokens
    if current_input is not None:
        # 当前输入可为 str | 多模态数组（附件）——数组按部件估算（base64 不入）
        input_tokens = (
            _content_part_tokens(current_input) if isinstance(current_input, list) else estimate_tokens(current_input)
        )
        if input_tokens >= remaining:
            raise ContextBudgetError(
                f"当前输入约 {input_tokens} tokens，超过剩余预算 {remaining}（请缩短内容或减少历史）"
            )
        remaining -= input_tokens

    # ③ 注入上下文截断
    injection: str | None = None
    if injected_context:
        inject_tokens = estimate_tokens(injected_context)
        allotment = int(remaining * 0.2)  # 初始调优参考比例（设计 3.4.5 ③）
        if inject_tokens <= allotment:
            injection = injected_context
            remaining -= inject_tokens
        elif allotment > 50:
            keep_chars = allotment * 2
            injection = injected_context[:keep_chars] + "…（注入上下文已截断）"
            remaining -= estimate_tokens(injection)

    # ④ 历史按原子单元从新到旧装填，保底 MIN_KEEP_UNITS
    # 工具结果截 4000 字（对齐 state 回填口径）：此前无条件截 200 字——列表型工具
    # （工作流列表/媒体搜索）模型永远只见首条前缀，「返回结果被截断」真机实锤的
    # 真凶在这是组装层无条件截断、与预算无关（预算裁剪只兜超限尾部）。不修改原
    # 对象——新建截断版 ToolMessage 保持 tool_call_id 配对；超预算仍由 _trim_unit 兜底
    trimmed_history: list[BaseMessage] = []
    for message in history:
        if isinstance(message, ToolMessage) and len(str(message.content)) > TOOL_RESULT_HISTORY_LIMIT:
            trimmed_history.append(
                ToolMessage(
                    content=truncate_tool_result(str(message.content), limit=TOOL_RESULT_HISTORY_LIMIT),
                    tool_call_id=message.tool_call_id or "",
                    name=message.name,
                )
            )
        else:
            trimmed_history.append(message)
    units = _atomic_units(trimmed_history)
    kept: list[list[BaseMessage]] = []
    for unit in reversed(units):
        unit_tokens = sum(_message_tokens(m) for m in unit)
        if unit_tokens <= remaining:
            kept.append(unit)
            remaining -= unit_tokens
            continue
        if len(kept) < MIN_KEEP_UNITS:
            truncated = _truncate_single_unit(unit, remaining)
            if truncated is not None:
                kept.append(truncated)
                break  # 保底塞入后预算耗尽
        break

    messages: list[BaseMessage] = [SystemMessage(content=system_message)]
    if injection:
        messages.append(SystemMessage(content=f"[参考上下文]\n{injection}"))
    for unit in reversed(kept):
        messages.extend(unit)
    if current_input is not None:
        messages.append(_as_user_message(current_input))
    return messages


def _as_user_message(content: str | list) -> BaseMessage:
    """当前输入消息：content 保真透传（str | 多模态 Content Parts 数组）。"""
    from langchain_core.messages import HumanMessage

    return HumanMessage(content=content)
