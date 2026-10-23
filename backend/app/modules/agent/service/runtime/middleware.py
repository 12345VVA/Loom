"""AgentMiddleware 协议（设计 3.4.3，附录 B 为权威签名）+ 四个内置中间件。

钩子触发序列（spike 实证）：before_agent（run 开始）→ [pre_model → 模型 → after_model]×N →
[wrap_tool → 工具执行]×M → after_agent（run 结束）。一期不开放用户自定义 middleware。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from langchain_core.messages import BaseMessage, SystemMessage

from app.modules.agent.service.runtime import prompt_render
from app.modules.agent.service.runtime.memory_service import estimate_tokens


@dataclass
class RunContext:
    """一次 run 的身份与定位信息（ctx，贯穿五钩子）。"""

    user_id: int
    user_name: str = ""
    is_super_admin: bool = False
    run_mode: str = "published"  # draft/published
    profile_id: int = 0
    session_id: int = 0
    trace_id: int | None = None


@runtime_checkable
class AgentMiddleware(Protocol):
    """五钩子协议：全部为可选实现（hasattr 判别）。"""

    def before_agent(self, ctx: RunContext) -> None: ...

    def pre_model(self, state: dict, ctx: RunContext) -> dict | None: ...

    def wrap_tool(self, name: str, args: dict, ctx: RunContext) -> dict: ...

    def after_model(self, state: dict, ctx: RunContext) -> None: ...

    def after_agent(self, ctx: RunContext) -> None: ...


class ToolDenied(Exception):
    """wrap_tool 拒绝执行（ToolExecutor 转为该工具的失败 ToolMessage）。"""


# --- 内置中间件 ---


class GuardrailsMiddleware:
    """护栏完整性验证（验收 11①）：唯一注入点在 prompt_render.render，
    此处仅校验 system 消息开头与版本标记——缺失/被模板内容移除 → fail-close 拒绝本次调用。"""

    def pre_model(self, state: dict, ctx: RunContext) -> dict | None:
        for message in state.get("messages") or []:
            if isinstance(message, SystemMessage):
                if not prompt_render.is_guardrails_intact(message.content):
                    raise RuntimeError("护栏完整性校验失败：system 消息缺少安全边界前置（fail-close）")
                return None  # 只校验首条 system
        raise RuntimeError("护栏完整性校验失败：缺少 system 消息（fail-close）")


class MemoryInjectionMiddleware:
    """记忆上下文注入（enable_memory 开启时）：context_provider 产出注入文本，
    交由裁剪器（build_model_messages）按预算消费。"""

    def __init__(self, context_provider=None):
        self._provider = context_provider  # Callable[[RunContext], str] | None

    def pre_model(self, state: dict, ctx: RunContext) -> dict | None:
        if self._provider is None:
            return None
        text = self._provider(ctx) or ""
        return {"injected_context": text} if text else None


class ToolAuthMiddleware:
    """工具授权（设计 3.3 执行安全性实时判定）：绑定名单 + 资源层启停 + level + 允许列表。

    checker: Callable[[str], None]——由 ToolExecutor 注入 assert_execution_allowed 的部分绑定；
    拒绝即 raise ToolDenied（不中止一轮内其他工具）。
    """

    def __init__(self, checker):
        self._checker = checker

    def wrap_tool(self, name: str, args: dict, ctx: RunContext) -> dict:
        self._checker(name)
        return args


class ToolTimingMiddleware:
    """工具计时 + 落库回调（观测二级 tool_call_log 的写入由 trace_service 注入）。"""

    def __init__(self, on_finish=None):
        self._on_finish = on_finish  # Callable[[name, args_summary, result_summary, ms, success, error], None]

    def wrap_tool(self, name: str, args: dict, ctx: RunContext) -> dict:
        # 计时由 ToolExecutor 承担（wrap 与执行同处同步流）；本中间件保留协议位置
        return args

    def after_model(self, state: dict, ctx: RunContext) -> None:
        return None


def apply_pre_model_hooks(middlewares: list, state: dict, ctx: RunContext) -> dict:
    """依序执行 pre_model 钩子并合并 state delta（后写覆盖先写）。"""
    delta: dict = {}
    for middleware in middlewares:
        hook = getattr(middleware, "pre_model", None)
        if callable(hook):
            result = hook(state, ctx)
            if result:
                delta.update(result)
    return delta


def apply_wrap_tool(middlewares: list, name: str, args: dict, ctx: RunContext) -> dict:
    """依序执行 wrap_tool 钩子（拒绝链：任一 raise 即终止）。"""
    for middleware in middlewares:
        hook = getattr(middleware, "wrap_tool", None)
        if callable(hook):
            args = hook(name, args, ctx) or args
    return args


def measure_state_tokens(state: dict) -> int:
    """观测辅助：估算 state.messages 的 token 占用。"""
    messages: list[BaseMessage] = state.get("messages") or []
    return sum(estimate_tokens(str(m.content)) for m in messages)


_ = field  # 保持 dataclass 导入完整（RunContext 未来扩展用）
