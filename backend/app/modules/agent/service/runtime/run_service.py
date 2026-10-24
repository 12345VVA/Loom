"""RunService：三层预算 + 终态机 + 超限/终止处置（设计 3.4.4）。

P3 本文件承载纯逻辑（RunBudget / 兜底回复 / 同构处置）；invoke/stream 的会话编排与
SSE 事件队列在 P5 落地（依赖发布快照与会话服务）。

预算触发一致性：任一运行层预算耗尽 → 注入明示原因的兜底回复 → 终态 completed
（受控结束非失败；error 备注记录触发项）；timed_out 仅总时限、failed 仅致命错误。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from sqlmodel import select

from app.modules.agent.model.agent import (
    AGENT_RUN_COMPLETED,
    AGENT_RUN_MODE_PUBLISHED,
    AGENT_RUN_RUNNING,
    AGENT_RUN_TIMED_OUT,
    AgentProfile,
    AgentToolCallLog,
)
from app.modules.agent.service.runtime.memory_service import AGENT_RUN_TOKEN_BUDGET
from app.modules.agent.service.runtime.tool_executor import ToolExecutor

logger = logging.getLogger("agent.run_service")
from app.modules.agent.service.runtime.run_lock import acquire_run_lock, owns_run_lock, release_run_lock

# 预算常量（设计 3.4.4 三层预算表；模块级便于测试覆写）
MODEL_CALLS_MULTIPLIER = 1  # model_calls 上限 = max_tool_rounds + 1（每轮工具后一次模型调用 + 收尾）
TOOL_CALLS_MULTIPLIER = 4  # tool_calls 上限 = 4 × max_tool_rounds（防异常硬限制，非完成保证）

_BUDGET_FALLBACKS = {
    "tool_rounds": "已达到本智能体配置的工具迭代轮数上限，以下为基于当前信息的回答。",
    "model_calls": "已达到本次运行的模型调用预算上限，以下为基于当前信息的回答。",
    "tool_calls": "已达到本次运行的工具调用次数上限，以下为基于当前信息的回答。",
    "run_tokens": "已达到本次运行的 token 预算上限，以下为基于当前信息的回答。",
}


def _context_token_budget(chain_window_min: int | None, max_tokens: int) -> int:
    """单次输入上下文预算（E15 动态化）：min(解析链最小窗口 − 输出上限, 常数下限)，
    下限保护防止异常小窗口把预算挤成负数/极小值（常数下限兜底，仍是「上界收紧」方向）。"""
    from app.modules.agent.service.runtime.memory_service import AGENT_CONTEXT_TOKEN_BUDGET

    if chain_window_min is None:  # 理论不可达（assert_window_for_budget 已拒绝 None）
        return AGENT_CONTEXT_TOKEN_BUDGET
    return max(1000, min(AGENT_CONTEXT_TOKEN_BUDGET, chain_window_min - int(max_tokens or 0)))


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


# ============ P5：会话运行编排（设计 3.4.4 stream/invoke + 评审 9 受控事件队列） ============

import queue as queue_mod
import threading
import uuid
from datetime import UTC
from datetime import datetime as _dt

from langchain_core.messages import HumanMessage as _HumanMessage
from langchain_core.messages import ToolMessage as _ToolMessage

from app.modules.agent.model.agent import (
    AGENT_RUN_CANCELLED,
    AGENT_RUN_COMPLETED,
    AGENT_RUN_FAILED,
    AGENT_RUN_TIMED_OUT,
    AgentMessage,
    AgentRunTrace,
    AgentSession,
)

CANCEL_KEY_PREFIX = "agent:cancel:"
HEARTBEAT_INTERVAL_SECONDS = 15  # SSE 心跳注释帧（长时模型调用保活，parseSse 跳 ':' 行）
FINAL_EVENT_TYPES = {"final", "error", "cancelled", "timed_out"}  # 一次 run 恰一个终态事件


@dataclass
class RunEvent:
    """受控事件队列单元（评审 9）：执行线程 emit 入队，SSE 线程出队。"""

    type: str
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.monotonic)


class RunHandle:
    """进程内 run 句柄：取消的本地快速路径 + 终态后事件出口永久关闭（评审 P1-4）。"""

    def __init__(self, trace_id: int, trace_token: str, session_id: int, deadline: RunDeadline):
        self.trace_id = trace_id
        self.trace_token = trace_token  # 锁值/取消键（跨 worker 唯一标识）
        self.session_id = session_id
        self.cancel_event = threading.Event()
        self.deadline = deadline
        self.closed = False
        self.event_queue: queue_mod.Queue[RunEvent | None] = queue_mod.Queue()

    def emit(self, event_type: str, payload: dict | None = None) -> None:
        """终态后事件出口永久关闭：残留工具线程的 emit 一律丢弃。"""
        if self.closed:
            return
        self.event_queue.put(RunEvent(event_type, payload or {}))

    def close(self, event_type: str, payload: dict | None = None) -> None:
        """终态事件（final/error/cancelled/timed_out 互斥）+ 关闭出口 + 哨兵唤醒。"""
        if self.closed:
            return
        self.event_queue.put(RunEvent(event_type, payload or {}))
        self.closed = True
        self.event_queue.put(None)


# --- 取消令牌（跨 worker：Redis 键 + 本地 Event 双查，评审）---


def _cancel_key(trace_token: str) -> str:
    return f"{CANCEL_KEY_PREFIX}{trace_token}"


def set_cancel_token(trace_token: str, timeout_seconds: int) -> None:
    """跨 worker 取消：写 Redis 键（TTL=run 时限）；本地句柄 Event 由 stop_run 同步置位。"""
    from app.modules.base.service.cache_service import cache_set

    cache_set(_cancel_key(trace_token), "1", ttl_seconds=max(60, timeout_seconds))


def is_cancel_requested(trace_token: str, handle: RunHandle | None) -> bool:
    """双查：本地 Event 快速路径 + Redis（跨 worker）。Redis 不可用仅依赖本地。"""
    if handle is not None and handle.cancel_event.is_set():
        return True
    try:
        from app.modules.base.service.cache_service import cache_get

        return bool(cache_get(_cancel_key(trace_token)))
    except Exception:  # noqa: BLE001
        return False


# --- SSE 帧形态（复用 ai stream 先例：data: json\n\n；心跳为注释帧）---


def sse_frame(event_type: str, payload: dict | None = None) -> str:
    import json as _json

    body = {"type": event_type, "payload": payload or {}, "ts": _dt.now(UTC).isoformat(timespec="seconds")}
    return f"data: {_json.dumps(body, ensure_ascii=False)}\n\n"


HEARTBEAT_FRAME = ": ping\n\n"


class AgentRunService:
    """run 编排：请求线程做校验链与发起，工作线程自建 Session 执行（Session 纪律，评审 P0-2）。"""

    def __init__(self, session: Any):
        self.session = session  # 请求线程 Session（校验/trace 创建/用户消息；绝不传入工作线程）

    # --- 发起校验链（评审 v1.4 五项 + 对象级权限）---

    def _load_profile_checked(self, profile_id: int, run_mode: str) -> Any:
        from app.modules.agent.service.tool_registry import degraded_error

        if degraded_error():
            raise HTTPException(status_code=503, detail=f"智能体工具注册表不可用（degraded）：{degraded_error()}")
        profile = self.session.get(AgentProfile, profile_id)
        if profile is None or profile.delete_time is not None:
            raise HTTPException(status_code=404, detail="智能体不存在")
        if not profile.enabled:
            raise HTTPException(status_code=400, detail="该智能体已被停用，无法发起对话")  # D14 实时控制
        return profile

    def _load_payload(self, profile: Any, run_mode: str) -> dict:
        """published=当前快照（D15 渠道动态依赖，每次 run 实时解析）；draft=最新草稿。"""
        from app.modules.agent.service.profile_service import AgentProfileService, build_draft_json
        from app.modules.agent.service.tool_registry import get_tool

        if run_mode == AGENT_RUN_MODE_PUBLISHED:
            from app.modules.agent.service.profile_service import assert_window_for_budget

            service = AgentProfileService(self.session)
            payload = service.get_current_snapshot(profile.id)
            if payload is None:
                raise HTTPException(status_code=400, detail="该智能体尚未发布，请先发布或使用调试台")
            tools = payload.get("toolResourceSnapshots") or []
            snapshot_tools = {t["toolName"]: {"level": t["level"], "parameters": t["parameters"]} for t in tools}
            max_tokens = int((payload.get("profile") or {}).get("maxTokens") or 4000)
            # E15 动态重校验：解析链最小窗口未知或不足预算 → run 拒绝（渠道档案可能发布后被修改）
            model_profile_code = payload.get("modelProfileCode") or profile.model_profile_code
            chain_min = assert_window_for_budget(self.session, model_profile_code, max_tokens)
            system_prompt = (payload.get("profile") or {}).get("systemPrompt")
            return {
                "model_profile_code": model_profile_code,
                "system_prompt": system_prompt,
                "snapshot_tools": snapshot_tools,
                "bound_names": set(payload.get("tools") or []),
                "max_tokens": max_tokens,
                "context_window_min": chain_min,
                "context_token_budget": _context_token_budget(chain_min, max_tokens),
                "temperature": (payload.get("profile") or {}).get("temperature", 0.5),
                "max_tool_rounds": (payload.get("profile") or {}).get("maxToolRounds", 12),
                "timeout_seconds": (payload.get("profile") or {}).get("timeoutSeconds", 60),
                "enable_memory": (payload.get("profile") or {}).get("enableMemory", True),
            }
        # draft：最新草稿（评审 P1-1——调试台永远最新）；工具面现场构建并逐个校验
        draft_json = json.loads(build_draft_json(profile))
        profile_fields = draft_json["profile"]
        from app.modules.agent.service.profile_service import assert_window_for_budget

        chain_min = assert_window_for_budget(
            self.session, profile.model_profile_code, int(profile_fields.get("maxTokens") or 0)
        )
        snapshot_tools: dict[str, dict] = {}
        for name in draft_json["tools"]:
            tool = get_tool(name)
            if tool is None:
                raise HTTPException(status_code=400, detail=f"调试台：工具 {name} 未注册")
            snapshot_tools[name] = {"level": tool.level, "parameters": tool.parameters}
        return {
            "model_profile_code": profile.model_profile_code,
            "system_prompt": profile_fields.get("systemPrompt"),
            "snapshot_tools": snapshot_tools,
            "bound_names": set(draft_json["tools"]),
            "max_tokens": profile_fields.get("maxTokens", 4000),
            "context_window_min": chain_min,
            "context_token_budget": _context_token_budget(chain_min, int(profile_fields.get("maxTokens") or 0)),
            "temperature": profile_fields.get("temperature", 0.5),
            "max_tool_rounds": profile_fields.get("maxToolRounds", 12),
            "timeout_seconds": profile_fields.get("timeoutSeconds", 60),
            "enable_memory": profile_fields.get("enableMemory", True),
        }

    def _resolve_session(
        self, *, profile: Any, session_id: int | None, question: str, run_mode: str, current_user: Any
    ) -> AgentSession:
        """会话属主 / session-profile 一致性 / run_mode 隔离（对象级权限，service 层强制）。"""
        import secrets

        if session_id is not None:
            row = self.session.get(AgentSession, session_id)
            if row is None or row.delete_time is not None:
                raise HTTPException(status_code=404, detail="会话不存在")
            if row.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="仅会话属主可发起对话")
            if row.profile_id != profile.id:
                raise HTTPException(status_code=400, detail="会话与智能体不一致，禁止借会话切换上下文")
            if row.run_mode != run_mode:
                raise HTTPException(status_code=400, detail="会话运行模式与请求不一致（draft/published 隔离）")
            return row
        row = AgentSession(
            session_code=f"ags-{secrets.token_hex(6)}",
            profile_id=profile.id,
            user_id=current_user.id,
            title=(question or "新会话")[:50],
            run_mode=run_mode,
            last_message_at=_dt.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    # --- stream（SSE）---

    def stream_run(self, *, profile_id: int, session_id: int | None, question: str, run_mode: str, current_user: Any):
        """发起 run 并返回 SSE StreamingResponse（受控事件队列 + 工作线程，评审 9）。"""
        from fastapi.responses import StreamingResponse

        profile = self._load_profile_checked(profile_id, run_mode)
        session_row = self._resolve_session(
            profile=profile, session_id=session_id, question=question, run_mode=run_mode, current_user=current_user
        )
        trace_token = uuid.uuid4().hex
        # 同会话串行锁（评审 P0-3：锁值 = trace_token；失败即拒绝）
        if not acquire_run_lock(session_row.id, trace_token, int(profile.timeout_seconds or 60)):
            raise HTTPException(status_code=409, detail="上一次调用尚未结束，请稍候或停止前一次运行")
        deadline = RunDeadline(int(profile.timeout_seconds or 60))
        handle = RunHandle(trace_id=0, trace_token=trace_token, session_id=session_row.id, deadline=deadline)
        _register_handle(handle)

        try:
            job = self._build_job(
                profile=profile,
                session_row=session_row,
                question=question,
                run_mode=run_mode,
                current_user=current_user,
                handle=handle,
                stream_answer=True,  # E1：SSE 会话启用 token 流式
            )
        except Exception:
            # 发起段校验失败（未发布/窗口不足/degraded 等）：锁必须随失败释放，
            # 否则会话被 TTL 残留锁死（E15 动态窗口拒绝路径会常态踩中）
            release_run_lock(session_row.id, trace_token)
            _unregister_handle(handle)
            raise
        worker = threading.Thread(
            target=self._execute_run, args=(job,), name=f"agent-run-{trace_token[:8]}", daemon=True
        )
        worker.start()

        def generator():
            yield sse_frame("run_started", {"traceToken": trace_token, "sessionId": session_row.id})
            while True:
                try:
                    event = handle.event_queue.get(timeout=HEARTBEAT_INTERVAL_SECONDS)
                except queue_mod.Empty:
                    yield HEARTBEAT_FRAME  # 心跳保活（长时模型调用，R2）
                    continue
                if event is None:
                    break
                yield sse_frame(event.type, event.payload)
            _unregister_handle(handle)

        return StreamingResponse(generator(), media_type="text/event-stream")

    # --- invoke（调试台同步；内部同执行路径）---

    def invoke_run(
        self, *, profile_id: int, session_id: int | None, question: str, run_mode: str, current_user: Any
    ) -> dict:
        profile = self._load_profile_checked(profile_id, run_mode)
        session_row = self._resolve_session(
            profile=profile, session_id=session_id, question=question, run_mode=run_mode, current_user=current_user
        )
        trace_token = uuid.uuid4().hex
        if not acquire_run_lock(session_row.id, trace_token, int(profile.timeout_seconds or 60)):
            raise HTTPException(status_code=409, detail="上一次调用尚未结束，请稍候或停止前一次运行")
        handle = RunHandle(
            trace_id=0,
            trace_token=trace_token,
            session_id=session_row.id,
            deadline=RunDeadline(int(profile.timeout_seconds or 60)),
        )
        _register_handle(handle)
        try:
            job = self._build_job(
                profile=profile,
                session_row=session_row,
                question=question,
                run_mode=run_mode,
                current_user=current_user,
                handle=handle,
            )
        except Exception:
            # 发起段校验失败（未发布/窗口不足/degraded 等）：锁必须随失败释放（同 stream_run）
            release_run_lock(session_row.id, trace_token)
            _unregister_handle(handle)
            raise
        try:
            self._execute_run(job)  # 同步执行（请求线程；Session 纪律同工作线程——self.session 不传入）
            final_event = None
            while True:
                event = handle.event_queue.get(timeout=HEARTBEAT_INTERVAL_SECONDS)
                if event is None:
                    break
                if event.type in FINAL_EVENT_TYPES:
                    final_event = event
            return {
                "traceToken": trace_token,
                "sessionId": session_row.id,
                "status": (final_event.payload or {}).get("status") if final_event else AGENT_RUN_COMPLETED,
                "payload": (final_event.payload if final_event else {}) or {},
            }
        finally:
            _unregister_handle(handle)

    # --- 停止（取消三层语义之一：令牌置位）---

    def stop_run(self, trace_token: str, current_user: Any) -> dict:
        handle = _get_handle(trace_token)
        if handle is None:
            return {"stopped": False, "message": "运行不存在或已结束（可能属其他实例，取消令牌将生效于执行侧）"}
        trace = self.session.get(AgentRunTrace, handle.trace_id) if handle.trace_id else None
        if trace is not None and trace.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="仅可停止本人发起的运行")
        handle.cancel_event.set()  # 本地快速路径
        set_cancel_token(trace_token, max(60, int(handle.deadline.remaining()) + 30))  # 跨 worker
        return {"stopped": True, "message": "取消请求已收到（停止调度待执行侧确认）"}

    # --- 任务装配（请求线程收尾）---

    def _build_job(
        self,
        *,
        profile: Any,
        session_row: AgentSession,
        question: str,
        run_mode: str,
        current_user: Any,
        handle: RunHandle,
        stream_answer: bool = False,  # E1：SSE 会话启用最终答案 token 流式；invoke 保持整段
    ) -> dict:
        """请求线程收尾：校验链（载荷/窗口）→ trace 落库 + 用户消息 → 工作线程任务包。"""
        payload = self._load_payload(profile, run_mode)
        trace = AgentRunTrace(
            profile_id=profile.id,
            run_mode=run_mode,
            snapshot_id=self._current_snapshot_id(profile.id, run_mode),
            agent_code=profile.code,
            agent_name=profile.name,
            session_id=session_row.id,
            user_id=current_user.id,
            status=AGENT_RUN_RUNNING,
            error=f"token:{handle.trace_token}",  # trace_token 随 trace 落库（stopStream 按 token 定位）
        )
        self.session.add(trace)
        self.session.commit()
        self.session.refresh(trace)
        user_message = AgentMessage(session_id=session_row.id, role="user", content=question)
        self.session.add(user_message)
        self.session.commit()
        handle.trace_id = trace.id
        return {
            "trace_id": trace.id,
            "session_id": session_row.id,
            "question": question,
            "run_mode": run_mode,
            "stream_answer": stream_answer,
            "engine": self.session.get_bind(),  # 请求线程的引擎（工作线程自建 Session 用；非 Session）
            "user": {
                "id": current_user.id,
                "name": getattr(current_user, "name", "") or "",
                "is_super_admin": bool(getattr(current_user, "is_super_admin", False)),
            },
            "payload": payload,
            "handle": handle,
        }

    def _current_snapshot_id(self, profile_id: int, run_mode: str) -> int | None:
        if run_mode != AGENT_RUN_MODE_PUBLISHED:
            return None
        from app.modules.agent.model.agent import AgentProfilePublishRecord

        record = self.session.exec(
            select(AgentProfilePublishRecord).where(
                AgentProfilePublishRecord.profile_id == profile_id,
                AgentProfilePublishRecord.is_current == True,  # noqa: E712
            )
        ).first()
        return record.snapshot_id if record else None

    # --- 工作线程执行（自建独立 Session，评审 P0-2）---

    def _execute_run(self, job: dict) -> None:
        from sqlmodel import Session as SqlSession

        from app.core.database import engine as app_engine
        from app.modules.agent.service.runtime import prompt_render
        from app.modules.agent.service.runtime.graph import GraphDeps, build_agent_graph
        from app.modules.agent.service.runtime.memory_service import (
            ContextBudgetError,
            estimate_tokens,
        )
        from app.modules.agent.service.runtime.model_wrapper import LoomChatModel
        from app.modules.ai.service.runtime_service import AiModelRuntimeService

        handle: RunHandle = job["handle"]
        payload = job["payload"]
        started = time.monotonic()

        def should_cancel() -> bool:
            return (
                is_cancel_requested(handle.trace_token, handle)
                or handle.deadline.expired()
                or not owns_run_lock(session_row.id, handle.trace_token)  # 锁所有权丢失自停（P0-3）
            )

        run_engine = job.get("engine") or app_engine  # 引擎注入（请求线程 bind；非 Session——纪律 P0-2）
        with SqlSession(run_engine) as db:  # 工作线程自建独立 Session
            trace: AgentRunTrace = db.get(AgentRunTrace, job["trace_id"])
            session_row: AgentSession = db.get(AgentSession, job["session_id"])
            try:
                runtime = AiModelRuntimeService(db)
                budget = RunBudget(max_tool_rounds=int(payload["max_tool_rounds"]))
                job["_budget"] = budget  # 终态落库读 tool_calls 累计
                model = LoomChatModel(
                    model_profile_code=_profile_code_of(job),
                    temperature=payload["temperature"],
                    max_tokens=payload["max_tokens"],
                    profile_source=job["run_mode"],
                    timeout_seconds=handle.deadline.per_request_timeout(payload["timeout_seconds"]),
                    min_context_window=payload.get("context_window_min"),  # E15：回退路径窗口约束
                )
                model._runtime_service = runtime  # noqa: SLF001 —— 单 run 装配（实例纪律）
                model._caller = _SimpleUser(job["user"])  # noqa: SLF001
                model._task_id = trace.id  # noqa: SLF001 —— R5 task_id 审计通道

                tool_ctx = _ToolCtx(
                    db=db,
                    user_id=job["user"]["id"],
                    user_name=job["user"]["name"],
                    is_super_admin=job["user"]["is_super_admin"],
                    trace_id=trace.id,
                    run_mode=job["run_mode"],
                )

                def log_tool_call(**kwargs):
                    db.add(AgentToolCallLog(trace_id=trace.id, **kwargs))
                    db.commit()

                executor = ToolExecutor(
                    snapshot_tools=payload["snapshot_tools"],
                    bound_names=payload["bound_names"],
                    context=tool_ctx,
                    should_cancel=should_cancel,
                    log_tool_call=log_tool_call,
                    on_event=handle.emit,
                )
                system_message = prompt_render.render(payload["system_prompt"], {"user_name": job["user"]["name"]})

                def validate_guardrails(messages):
                    from langchain_core.messages import SystemMessage as _Sys

                    if (
                        not messages
                        or not isinstance(messages[0], _Sys)
                        or not prompt_render.is_guardrails_intact(messages[0].content)
                    ):
                        raise RuntimeError("护栏完整性校验失败（fail-close）")

                deps = GraphDeps(
                    model=model,
                    tool_executor=executor,
                    budget=budget,
                    system_message=system_message,
                    tool_schema_tokens=estimate_tokens(
                        json.dumps(list(payload["snapshot_tools"].values()), ensure_ascii=False)
                    ),
                    max_tool_rounds=int(payload["max_tool_rounds"]),
                    context_token_budget=int(payload.get("context_token_budget") or 0)
                    or None,  # E15 动态输入预算（None 走常数下限）
                    stream_answer=bool(job.get("stream_answer")),  # E1：仅 SSE 会话启用
                    guardrails_validator=validate_guardrails,
                    on_event=handle.emit,
                    should_cancel=should_cancel,
                )
                graph = build_agent_graph(deps)
                state = graph.invoke(
                    {"messages": [_HumanMessage(content=job["question"])], "model_calls": 0, "tool_rounds": 0}
                )
                # 终态判定（正常完成路径同样检查取消/超时——should_cancel 使图软停止自然走完，
                # 终态不得误标 completed，验收 19/取消语义）
                if is_cancel_requested(handle.trace_token, handle):
                    self._finish_run(db, job, state, AGENT_RUN_CANCELLED, started, "已请求取消")
                    handle.close("cancelled", {"message": "运行已取消"})
                elif handle.deadline.expired():
                    self._finish_run(db, job, state, AGENT_RUN_TIMED_OUT, started, "运行超时")
                    handle.close("timed_out", {"message": "运行超时"})
                else:
                    self._finish_run(db, job, state, AGENT_RUN_COMPLETED, started, None)
                    handle.close("final", self._final_payload(state, AGENT_RUN_COMPLETED))
            except ContextBudgetError as exc:
                self._finish_run(db, job, None, AGENT_RUN_FAILED, started, f"上下文预算：{exc}")
                handle.close("error", {"message": str(exc)})
            except Exception as exc:  # noqa: BLE001 —— 终态机：致命错误 failed（⑦ 同构处置见 _finish_run）
                logger.exception("agent run 执行失败 trace=%s", trace.id)
                if is_cancel_requested(handle.trace_token, handle):
                    self._finish_run(db, job, None, AGENT_RUN_CANCELLED, started, "已请求取消")
                    handle.close("cancelled", {"message": "运行已取消"})
                elif handle.deadline.expired():
                    self._finish_run(db, job, None, AGENT_RUN_TIMED_OUT, started, "运行超时")
                    handle.close("timed_out", {"message": "运行超时"})
                else:
                    self._finish_run(db, job, None, AGENT_RUN_FAILED, started, str(exc))
                    handle.close("error", {"message": str(exc)[:300]})
            finally:
                release_run_lock(job["session_id"], handle.trace_token)

    def _finish_run(
        self, db: Any, job: dict, state: dict | None, status: str, started: float, error: str | None
    ) -> None:
        """终态落库：trace 计数/状态 + assistant/tool 消息入库 + ⑦ 同构处置兜底。"""
        trace: AgentRunTrace = db.get(AgentRunTrace, job["trace_id"])
        session_row: AgentSession = db.get(AgentSession, job["session_id"])
        handle: RunHandle = job["handle"]
        if state is not None:
            messages = list(state.get("messages") or [])
            for m in messages:
                if isinstance(m, _HumanMessage):
                    continue  # 用户消息已在发起时落库
                role = (
                    "assistant"
                    if getattr(m, "type", "") == "ai"
                    else ("tool" if isinstance(m, _ToolMessage) else "user")
                )
                db.add(
                    AgentMessage(
                        session_id=session_row.id,
                        role=role,
                        content=m.content if isinstance(m.content, str) else str(m.content),
                        name=getattr(m, "name", None),
                        tool_call_id=getattr(m, "tool_call_id", None),
                    )
                )
            budget: RunBudget = _budget_of(job)
            trace.model_calls = int(state.get("model_calls") or 0)
            trace.tool_rounds = int(state.get("tool_rounds") or 0)
            trace.tool_calls = budget.tool_calls
        elif error is not None and is_cancel_requested(handle.trace_token, handle):
            # 图未产出（异常终止）：⑦ 同构处置兜底由消息侧原子单元规则承担（无本轮 tool_calls 落库）
            pass
        trace.status = status
        trace.error = error
        trace.duration_ms = int((time.monotonic() - started) * 1000)
        db.add(trace)
        session_row.last_message_at = _dt.now(UTC)
        db.add(session_row)
        db.commit()

    def _final_payload(self, state: dict, status: str) -> dict:
        messages = list(state.get("messages") or [])
        final = messages[-1] if messages else None
        return {
            "status": status,
            "answer": str(final.content) if final is not None else "",
            "modelCalls": int(state.get("model_calls") or 0),
            "toolRounds": int(state.get("tool_rounds") or 0),
        }


# --- 进程内句柄注册表 ---


def _register_handle(handle: RunHandle) -> None:
    with _handles_guard:
        _run_handles[handle.trace_token] = handle


def _unregister_handle(handle: RunHandle) -> None:
    with _handles_guard:
        _run_handles.pop(handle.trace_token, None)


def _get_handle(trace_token: str) -> RunHandle | None:
    with _handles_guard:
        return _run_handles.get(trace_token)


def _find_token_in_trace(error: str | None) -> str | None:
    if error and error.startswith("token:"):
        return error.split(":", 1)[1]
    return None


def _profile_code_of(job: dict) -> str:
    """渠道 profile code：published 从快照载荷取（D15 渠道标识入快照），draft 从活表。"""
    payload = job["payload"]
    code = payload.get("model_profile_code")
    if code:
        return code
    return job["profile"].model_profile_code if hasattr(job.get("profile"), "model_profile_code") else ""


class _SimpleUser:
    """工作线程内的最小调用者形态（ai 审计归因用；不携带 ORM 实体跨线程）。"""

    def __init__(self, info: dict):
        self.id = info["id"]
        self.name = info.get("name", "")
        self.is_super_admin = bool(info.get("is_super_admin"))


# ToolContext 的运行时最小实现（agent_tools.ToolContext 的鸭子类型同构；避免循环导入）
class _ToolCtx:
    def __init__(
        self,
        db: Any,
        user_id: int,
        user_name: str = "",
        is_super_admin: bool = False,
        trace_id: int | None = None,
        run_mode: str = "",
    ):
        self.db = db
        self.user_id = user_id
        self.user_name = user_name
        self.is_super_admin = is_super_admin
        self.trace_id = trace_id
        self.run_mode = run_mode


_run_handles: dict[str, RunHandle] = {}
_handles_guard = threading.Lock()


def _budget_of(job: dict) -> RunBudget:
    budget = job.get("_budget")
    return budget if isinstance(budget, RunBudget) else RunBudget(max_tool_rounds=1)
