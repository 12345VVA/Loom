"""Run 作业包类型契约（架构审查 P0-3：替换裸 dict 作业包）。

job 与 payload 此前是无 schema 的 dict：字段名无静态检查、两个构造点（_build_job /
resume_trace）已出现字段漂移（resume 版有 group_id/trace_token 而无 handle）、
_budget/handle 靠运行时回写形成隐式协议。dataclass 化后：

- RunJob.budget 为正式字段（替代 job["_budget"] 运行时回写）；
- RunJob.handle 为正式字段（resume 侧构造后赋值，与原 job["handle"] 回写同语义）；
- run_mode 与 payload 的字段都是稳定 schema（_load_payload / _payload_from_snapshot
  构造，单点来源）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.agent.service.runtime.budget import RunBudget
    from app.modules.agent.service.runtime.run_service import RunHandle


@dataclass
class RunUser:
    """跨线程传递的最小用户形态（不携带 ORM 实体；_SimpleUser 消费）。"""

    id: int
    name: str = ""
    is_super_admin: bool = False


@dataclass
class RunPayload:
    """模型执行载荷（_load_payload draft / _payload_from_snapshot published 单点构造）。"""

    model_profile_code: str | None = None
    system_prompt: str | None = None
    snapshot_tools: dict[str, dict] = field(default_factory=dict)
    bound_names: set[str] = field(default_factory=set)
    max_tokens: int = 4000
    context_window_min: int | None = None
    context_token_budget: int | None = None
    temperature: float = 0.5
    max_tool_rounds: int = 12
    timeout_seconds: int = 60
    enable_memory: bool = True
    execution_mode: str = "chat"
    workflow_definition_id: int | None = None


@dataclass
class RunJob:
    """工作线程任务包：一次 run（或 E4 恢复轮）执行所需的全部输入。"""

    trace_id: int
    session_id: int
    run_mode: str
    user: RunUser
    payload: RunPayload
    question: str = ""
    attachment_metas: list = field(default_factory=list)
    stream_answer: bool = False
    # 请求线程 bind 的引擎（工作线程自建 Session 用；非 Session——纪律 P0-2）
    engine: Any = None
    handle: RunHandle | None = None
    # E4 恢复轮专属
    group_id: str | None = None
    trace_token: str | None = None
    # 终态落库读 tool_calls 累计（_build_runtime 装配时写入）
    budget: RunBudget | None = None
