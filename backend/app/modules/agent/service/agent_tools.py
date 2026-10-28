"""智能体内置系统工具 + ToolContext（工具 SPI 结构契约的 agent 侧示范实现）。

结构契约（设计 3.3，业务模块零 import agent，纯结构约定）：
各业务模块在 ``service/agent_tools.py`` 暴露 ``get_agent_tools() -> list[dict]``，每项::

    { "name": str（全局唯一，对外契约不可改名）,
      "description": str（进 LLM schema）,
      "display_name": str（可选，管理面人类可读名；缺省回落 tool_name）,
      "level": "readonly" | "reversible_write" | "dangerous_write"（必填，D11）,
      "args_model": type[pydantic.BaseModel]（生成 JSON schema + 服务端参数校验）,
      "func": def func(args: BaseModel, ctx: ToolContext) -> str }

身份经 ctx 注入、**不进 LLM 参数**（spike S4）；ctx.db 仅可在工具执行流内同步使用，
禁止把 Session 带出执行流（线程/异步任务）——3.4.1 顺序执行前提下共享安全。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlmodel import Session


def tool_result(payload: dict, *, ok: bool = True) -> str:
    """工具返回值统一序列化（给 LLM 消费的 JSON 字符串，不套响应信封）。

    软失败契约（B2）：工具内业务失败必须抛异常（HTTPException/ValueError——执行器
    归类审计）或 `tool_result(payload, ok=False)`（执行器识别为 success=False +
    skipped_reason='soft_failure'）；**禁止吞异常返回普通结果串**——那会在审计面
    记成「成功」。ok=True 时不注入 ok 键（返回形态与历史零变化）。"""
    if ok:
        return json.dumps(payload, ensure_ascii=False, default=str)
    return json.dumps({"ok": False, **payload}, ensure_ascii=False, default=str)


@dataclass
class ToolContext:
    """运行时注入的工具上下文（身份 + 会话），不进 LLM schema。"""

    db: Session
    user_id: int
    user_name: str = ""
    is_super_admin: bool = False
    trace_id: int | None = None
    run_mode: str = ""  # draft/published（工具可感知运行模式做差异化行为，首版只读工具不依赖）


class SystemInfoArgs(BaseModel):
    """system_info 无参数。"""


class CurrentTimeArgs(BaseModel):
    """current_time 无参数。"""


def system_info(args: SystemInfoArgs, ctx: ToolContext) -> str:
    """返回应用运行环境概要（只读、无敏感信息：不含配置值/密钥/路径细节）。"""
    import platform

    return tool_result(
        {
            "appName": "Loom",
            "python": platform.python_version(),
            "platform": platform.system(),
            "serverTime": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "智能体运行环境概要（只读）",
        }
    )


def current_time(args: CurrentTimeArgs, ctx: ToolContext) -> str:
    """返回服务器当前时间（ISO 8601 带时区）。"""
    return tool_result({"now": datetime.now().astimezone().isoformat(timespec="seconds")})


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "system_info",
            "display_name": "系统信息",
            "description": "查询当前系统的运行环境概要（应用名/Python 版本/平台/服务器时间）",
            "level": "readonly",
            "args_model": SystemInfoArgs,
            "func": system_info,
        },
        {
            "name": "current_time",
            "display_name": "当前时间",
            "description": "获取服务器当前时间（ISO 8601 带时区），用于回答时间相关问题",
            "level": "readonly",
            "args_model": CurrentTimeArgs,
            "func": current_time,
        },
    ]
