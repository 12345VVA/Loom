"""AgentMiddleware 协议（设计 3.4.3，附录 B 为权威签名）+ 记忆注入中间件。

钩子触发序列（spike 实证）：before_agent（run 开始）→ [pre_model → 模型 → after_model]×N →
[wrap_tool → 工具执行]×M → after_agent（run 结束）。一期不开放用户自定义 middleware。

与专用通道的职责边界（工具链路专题 P0-2 收口：只保留有实例化点与真实消费者的实现，
其余能力各有已接入的权威通道，勿再以中间件形态重复实现——原三个内置实现的教训：
Guardrails 按 state 校验而生产 state 永无 SystemMessage，接上即 fail-close 崩溃；
ToolAuth 与 _precheck 双跑授权且 HTTPException 会穿透 ToolDenied 捕获炸整轮；Timing 纯空壳）：

- 护栏完整性 → GraphDeps.guardrails_validator（校验组装后 messages，fail-close）；
- 工具授权/执行安全 → ToolExecutor._precheck 内联 assert_execution_allowed
  （拒绝落 skipped_reason="denied" 审计语义，单工具失败不中止一轮）；
- 工具计时/落库 → ToolExecutor._write_log（tool_call_log + 慢调用告警）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from langchain_core.messages import BaseMessage

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


def apply_pre_model_hooks(middlewares: list, state: dict, ctx: RunContext | None) -> dict:
    """依序执行 pre_model 钩子并合并 state delta（后写覆盖先写）。

    注意不捕获异常：钩子实现须自行兜底（如记忆检索失败降级为空串），
    否则异常将把整轮 run 打成 failed。"""
    delta: dict = {}
    for middleware in middlewares:
        hook = getattr(middleware, "pre_model", None)
        if callable(hook):
            result = hook(state, ctx)
            if result:
                delta.update(result)
    return delta


def apply_wrap_tool(middlewares: list, name: str, args: dict, ctx: RunContext | None) -> dict:
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
