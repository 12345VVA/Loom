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
from app.modules.agent.service.runtime.prompt_render import guardrails_version
from app.modules.agent.service.runtime.timing import logger as timing_logger
from app.modules.agent.service.runtime.timing import timed
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
        self.prompt_tokens = 0
        self.completion_tokens = 0
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
            # usage 已在 graph._call_model 归一为 snake_case 三键（兼容历史 camelCase 读法）
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            self.total_tokens += int(usage.get("total_tokens") or 0)
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
    AGENT_EXECUTION_MODE_WORKFLOW,
    AGENT_RUN_CANCELLED,
    AGENT_RUN_COMPLETED,
    AGENT_RUN_FAILED,
    AGENT_RUN_MODE_DRAFT,
    AGENT_RUN_TIMED_OUT,
    AGENT_RUN_WAITING_APPROVAL,
    AgentMessage,
    AgentProfileSnapshot,
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

    def close_suspended(self, payload: dict | None = None) -> None:
        """E4 审批挂起收尾：approval_required 后结束传输（连接结束 ≠ Run 终结，D27 三概念分离）。

        非终态事件——逻辑 Run 转 waiting_approval 待恢复；终态由恢复执行的新连接送达。
        """
        if self.closed:
            return
        self.event_queue.put(RunEvent("approval_required", payload or {}))
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
        from app.modules.agent.service.profile_service import build_draft_json
        from app.modules.agent.service.tool_registry import get_tool

        if run_mode == AGENT_RUN_MODE_PUBLISHED:
            from app.modules.agent.service.profile_service import AgentProfileService

            payload = AgentProfileService(self.session).get_current_snapshot(profile.id)
            if payload is None:
                raise HTTPException(status_code=400, detail="该智能体尚未发布，请先发布或使用调试台")
            return self._payload_from_snapshot(profile, payload)
        # draft：最新草稿（评审 P1-1——调试台永远最新）；工具面现场构建并逐个校验。
        # E17：编排型草稿不支持调试台试聊（draft 链路无 workflow 执行语义），引导走工作流试运行
        if getattr(profile, "execution_mode", "chat") == AGENT_EXECUTION_MODE_WORKFLOW:
            raise HTTPException(
                status_code=400,
                detail="编排型智能体不支持调试台试聊，请在工作流模块使用试运行验证",
            )
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

    def _payload_from_snapshot(self, profile: Any, payload: dict) -> dict:
        """快照载荷展开（published run 与 E4 恢复共用；恢复传挂起时快照而非 current，D13）。"""
        from app.modules.agent.service.profile_service import assert_window_for_budget

        # E17 编排模式段（chat 型旧快照缺省补齐）
        execution = payload.get("execution") or {}
        execution_mode = execution.get("mode") or "chat"
        tools = payload.get("toolResourceSnapshots") or []
        snapshot_tools = {t["toolName"]: {"level": t["level"], "parameters": t["parameters"]} for t in tools}
        max_tokens = int((payload.get("profile") or {}).get("maxTokens") or 4000)
        # E15 动态重校验：解析链最小窗口未知或不足预算 → run 拒绝（渠道档案可能发布后被修改）。
        # 编排模式（E17）不参与模型执行——跳过窗口断言（渠道仅作标识）。
        model_profile_code = payload.get("modelProfileCode") or profile.model_profile_code
        chain_min: int | None = None
        if execution_mode != AGENT_EXECUTION_MODE_WORKFLOW:
            chain_min = assert_window_for_budget(self.session, model_profile_code, max_tokens)
        return {
            "model_profile_code": model_profile_code,
            "system_prompt": (payload.get("profile") or {}).get("systemPrompt"),
            "snapshot_tools": snapshot_tools,
            "bound_names": set(payload.get("tools") or []),
            "max_tokens": max_tokens,
            "context_window_min": chain_min,
            "context_token_budget": _context_token_budget(chain_min, max_tokens) if chain_min else None,
            "temperature": (payload.get("profile") or {}).get("temperature", 0.5),
            "max_tool_rounds": (payload.get("profile") or {}).get("maxToolRounds", 12),
            "timeout_seconds": (payload.get("profile") or {}).get("timeoutSeconds", 60),
            "enable_memory": (payload.get("profile") or {}).get("enableMemory", True),
            "execution_mode": execution_mode,
            "workflow_definition_id": execution.get("workflowDefinitionId"),
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

    def stream_run(
        self,
        *,
        profile_id: int,
        session_id: int | None,
        question: str,
        attachments: list[int] | None = None,
        run_mode: str,
        current_user: Any,
    ):
        """发起 run 并返回 SSE StreamingResponse（受控事件队列 + 工作线程，评审 9）。"""
        from fastapi.responses import StreamingResponse

        req_started = time.perf_counter()
        trace_token = uuid.uuid4().hex

        with timed("req.profile", trace_token=trace_token):
            profile = self._load_profile_checked(profile_id, run_mode)
        with timed("req.session", trace_token=trace_token):
            session_row = self._resolve_session(
                profile=profile, session_id=session_id, question=question, run_mode=run_mode, current_user=current_user
            )
        # 同会话串行锁（评审 P0-3：锁值 = trace_token；失败即拒绝）
        with timed("req.lock", trace_token=trace_token):
            if not acquire_run_lock(session_row.id, trace_token, int(profile.timeout_seconds or 60)):
                raise HTTPException(status_code=409, detail="上一次调用尚未结束，请稍候或停止前一次运行")
        deadline = RunDeadline(int(profile.timeout_seconds or 60))
        handle = RunHandle(trace_id=0, trace_token=trace_token, session_id=session_row.id, deadline=deadline)
        _register_handle(handle)

        try:
            with timed("req.build_job", trace_token=trace_token):
                job = self._build_job(
                    profile=profile,
                    session_row=session_row,
                    question=question,
                    attachments=attachments or [],
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
        with timed("req.spawn", trace_token=trace_token):
            worker = threading.Thread(
                target=self._execute_run, args=(job,), name=f"agent-run-{trace_token[:8]}", daemon=True
            )
            worker.start()
        # 用户感知「点发送到首帧」的主体（不含首帧后模型生成时长——那在 worker 段/llm.round）
        timing_logger.info(
            "agent 请求发起段耗时",
            extra={
                "phase": "req.total",
                "duration_ms": int((time.perf_counter() - req_started) * 1000),
                "status": "ok",
                "trace_token": trace_token,
            },
        )

        def generator():
            try:
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
            finally:
                # 客户端断开（GeneratorExit）/流异常中断也必须注销，否则 handle
                # 泄漏——stop_run 的注册表将长期残留已死连接的令牌
                _unregister_handle(handle)

        return StreamingResponse(generator(), media_type="text/event-stream")

    # --- invoke（调试台同步；内部同执行路径）---

    def invoke_run(
        self,
        *,
        profile_id: int,
        session_id: int | None,
        question: str,
        attachments: list[int] | None = None,
        run_mode: str,
        current_user: Any,
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
                attachments=attachments or [],
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
            suspended_event = None
            while True:
                event = handle.event_queue.get(timeout=HEARTBEAT_INTERVAL_SECONDS)
                if event is None:
                    break
                if event.type == "approval_required":
                    suspended_event = event  # E4：挂起非终态——返回等待语义，不再等终态
                    break
                if event.type in FINAL_EVENT_TYPES:
                    final_event = event
            if suspended_event is not None:
                return {
                    "traceToken": trace_token,
                    "sessionId": session_row.id,
                    "status": AGENT_RUN_WAITING_APPROVAL,
                    "payload": suspended_event.payload,
                }
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
            # E4：挂起态 run（线程已结束、句柄已注销）——按 token 定位 waiting trace 直接取消
            return self._cancel_suspended_run(trace_token, current_user)
        trace = self.session.get(AgentRunTrace, handle.trace_id) if handle.trace_id else None
        if trace is not None and trace.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="仅可停止本人发起的运行")
        handle.cancel_event.set()  # 本地快速路径
        set_cancel_token(trace_token, max(60, int(handle.deadline.remaining()) + 30))  # 跨 worker
        return {"stopped": True, "message": "取消请求已收到（停止调度待执行侧确认）"}

    def _cancel_suspended_run(self, trace_token: str, current_user: Any) -> dict:
        """取消挂起中的 run（E4）：pending 行 → cancelled + 组 ToolMessage 补齐配对 + trace 终态。

        已终止的 run 不再交回模型继续（3.4.4 ⑦ 同构处置）——补齐后无模型续跑。
        """
        from app.modules.agent.model.agent import AGENT_RUN_CANCELLED as _CANCELLED
        from app.modules.agent.service import approval_service

        trace = self.session.exec(
            select(AgentRunTrace).where(
                AgentRunTrace.error == f"token:{trace_token}",
                AgentRunTrace.status == AGENT_RUN_WAITING_APPROVAL,
            )
        ).first()
        if trace is None:
            return {"stopped": False, "message": "运行不存在或已结束（可能属其他实例，取消令牌将生效于执行侧）"}
        if trace.user_id != current_user.id and not getattr(current_user, "is_super_admin", False):
            raise HTTPException(status_code=403, detail="仅可停止本人发起的运行")
        live = approval_service.suspended_group_of(self.session, trace.id)
        if live is not None:
            group_id = live[0]
            approval_service.cancel_group(self.session, trace_id=trace.id, group_id=group_id)
            ai_row, calls = _suspended_ai_of(self.session, trace.session_id, group_id)
            for call in calls:
                self.session.add(
                    AgentMessage(
                        session_id=trace.session_id,
                        role="tool",
                        content="运行已取消，该工具调用未执行",
                        name=call.get("name") or "",
                        tool_call_id=call.get("id") or "",
                    )
                )
        trace.status = _CANCELLED
        trace.error = "挂起中取消（审批未完成即终止）"
        trace.duration_ms = int(trace.execution_ms or 0)
        self.session.add(trace)
        self.session.commit()
        return {"stopped": True, "message": "挂起运行已取消，待审批调用全部关闭"}

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
        attachments: list[int] | None = None,
        stream_answer: bool = False,  # E1：SSE 会话启用最终答案 token 流式；invoke 保持整段
    ) -> dict:
        """请求线程收尾：校验链（载荷/窗口/附件）→ trace 落库 + 用户消息 → 工作线程任务包。"""
        # E4 会话阻塞：存在待审批调用 → 拒绝新 run（审批人权限不授予请求者；解锁=组终局）
        from app.modules.agent.service.approval_service import has_pending as approval_pending

        if approval_pending(self.session, session_row.id):
            raise HTTPException(status_code=409, detail="该会话存在待审批的工具调用，审批完成前不能发起新对话")
        payload = self._load_payload(profile, run_mode)
        self._assert_write_tools_ack(profile, payload)
        # 附件发起线程同步校验（SSE 建流前 400/403/404，好于流中 error 帧）
        attachment_metas = _validate_attachments(self.session, attachments or [], current_user)
        trace = AgentRunTrace(
            profile_id=profile.id,
            run_mode=run_mode,
            snapshot_id=self._current_snapshot_id(profile.id, run_mode),
            agent_code=profile.code,
            agent_name=profile.name,
            session_id=session_row.id,
            user_id=current_user.id,
            # D16：trace 记录本次 run 实际使用的护栏版本（安全策略实时生效可追溯）；
            # 编排型（E17）不经 LLM 护栏，记 None。
            guardrails_version=(
                None if payload.get("execution_mode") == AGENT_EXECUTION_MODE_WORKFLOW else guardrails_version()
            ),
            status=AGENT_RUN_RUNNING,
            error=f"token:{handle.trace_token}",  # trace_token 随 trace 落库（stopStream 按 token 定位）
        )
        self.session.add(trace)
        self.session.commit()
        self.session.refresh(trace)
        user_message = AgentMessage(session_id=session_row.id, role="user", content=question)
        if attachment_metas:
            # 附件引用仅落 meta 供前端渲染回显；content 保持纯文本（对齐「持久化历史≠模型上下文」）
            user_message.meta = json.dumps({"attachments": attachment_metas}, ensure_ascii=False)
        self.session.add(user_message)
        self.session.commit()
        # 连接已随 commit 归还池。此后至流结束前仅允许访问主键属性（trace.id /
        # session_row.id 走 identity map 不触发 SELECT）；任何非主键属性访问都会
        # refresh 并重新 checkout 连接，使 agent SSE 流式期间 DB 连接悬挂回归
        # （异步审查 P0-2；expire_on_commit=True 实测见报告 v3）——改这里前先读此注释
        handle.trace_id = trace.id
        return {
            "trace_id": trace.id,
            "session_id": session_row.id,
            "question": question,
            "attachment_metas": attachment_metas,
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

    def _assert_write_tools_ack(self, profile: Any, payload: dict) -> None:
        """E3 实时校验：载荷含可逆写工具 → write_tools_ack 必须在案（发布是第一道，发起是实时道；
        恢复路径不重校——挂起发起时已过，执行时刻另有整链校验）。"""
        from app.modules.agent.model.agent import AGENT_TOOL_LEVEL_REVERSIBLE_WRITE

        has_write = any(
            t.get("level") == AGENT_TOOL_LEVEL_REVERSIBLE_WRITE for t in (payload.get("snapshot_tools") or {}).values()
        )
        if has_write and not getattr(profile, "write_tools_ack", False):
            raise HTTPException(
                status_code=400,
                detail="该智能体绑定了写工具但未确认写工具知情声明（writeToolsAck），无法发起对话",
            )

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
        from app.modules.agent.service.runtime.graph import ApprovalSuspension, GraphDeps, build_agent_graph
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

        # ── 终态必达外圈：前置段（engine/Session/db.get）异常、_finish_run commit 抛错、
        # BaseException 不被内层 except Exception 覆盖——三类路径统一收口，保证
        # handle.close 必达（generator 否则无限心跳、前端永等终态）+ 锁必释放。
        try:
            run_engine = job.get("engine") or app_engine  # 引擎注入（请求线程 bind；非 Session——纪律 P0-2）
            with (
                timed("worker.db_setup", trace_token=handle.trace_token),
                SqlSession(run_engine) as db,
            ):  # 工作线程自建独立 Session
                trace: AgentRunTrace = db.get(AgentRunTrace, job["trace_id"])
                session_row: AgentSession = db.get(AgentSession, job["session_id"])
                # E17 编排模式分流：绑定工作流实例化执行（不经 graph/工具链；E1 流式/审批/预算不涉及）。
                # 锁释放必须随行（graph 分支在 finally 释放，一期锁残留缺陷的同构教训）——
                # 分支提前 return 前自行释放，防进程内降级锁 TTL 残留锁死同会话后续 run。
                if payload.get("execution_mode") == AGENT_EXECUTION_MODE_WORKFLOW:
                    try:
                        self._execute_workflow_run(db, job, trace, session_row, handle, payload, started)
                    finally:
                        release_run_lock(job["session_id"], handle.trace_token)
                    return
                try:
                    with timed("worker.wiring", trace_token=handle.trace_token):
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
                    with timed("worker.prompt_render", trace_token=handle.trace_token):
                        system_message = prompt_render.render(
                            payload["system_prompt"], {"user_name": job["user"]["name"]}
                        )

                    def validate_guardrails(messages):
                        from langchain_core.messages import SystemMessage as _Sys

                        if (
                            not messages
                            or not isinstance(messages[0], _Sys)
                            or not prompt_render.is_guardrails_intact(messages[0].content)
                        ):
                            raise RuntimeError("护栏完整性校验失败（fail-close）")

                    with timed("worker.graph_build", trace_token=handle.trace_token):
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
                            trace_token=handle.trace_token,
                        )
                        graph = build_agent_graph(deps)
                    with timed(
                        "worker.graph_invoke",
                        level=logging.INFO,
                        slow="phase",
                        trace_token=handle.trace_token,
                        message="agent graph 执行总耗时（含全部 LLM/工具轮）",
                    ):
                        # 附件 parts 在 worker 线程组装（请求线程只校验引用，文件读取不占请求线程）
                        initial_content = _build_initial_content(
                            job["question"], _build_attachment_parts(job.get("attachment_metas") or [])
                        )
                        state = graph.invoke(
                            {"messages": [_HumanMessage(content=initial_content)], "model_calls": 0, "tool_rounds": 0}
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
                except ApprovalSuspension as susp:
                    # E4 整组预检命中：本轮零执行 → 审批行 + 挂起 AI 消息 + trace=waiting_approval +
                    # approval_required（非终态，连接结束 ≠ Run 终结）；锁随 finally 释放（恢复时重取）
                    self._suspend_run(db, job, trace, session_row, handle, susp, started)
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
        except BaseException as exc:  # noqa: BLE001 —— worker 线程兜底（close 幂等，主路径已 close 时为 no-op）
            logger.exception("agent run 兜底终态 trace=%s token=%s", job.get("trace_id"), handle.trace_token)
            try:
                release_run_lock(job["session_id"], handle.trace_token)
            except Exception:  # noqa: BLE001 —— Redis 挂时不掩盖兜底主语义
                logger.exception("agent run 锁兜底释放失败 token=%s", handle.trace_token)
            handle.close("error", {"message": f"运行异常终止：{str(exc)[:200]}"})
            # 不 re-raise：终态已入队、锁已释放；daemon 工作线程自然结束（KeyboardInterrupt
            # 仅主线程、SystemExit 线程局部），再抛只会经 threading excepthook 重复打印同一堆栈

    def _execute_workflow_run(
        self,
        db: Any,
        job: dict,
        trace: AgentRunTrace,
        session_row: AgentSession,
        handle: RunHandle,
        payload: dict,
        started: float,
    ) -> None:
        """编排模式执行分支（E17）：快照绑定的工作流实例化执行，输出回写会话。

        语义边界：
        - 引用式绑定：执行走 definition 现行发布版（D13 冻结边界同工具语义快照），
          但发起前实时校验 is_active/已发布（D14 实时安全约束高于快照）；
        - 取消/超时传播到 workflow 实例（cancel_instance 以发起者身份——instance.user_id
          即 run 发起者，属主校验天然对齐）；
        - paused（工作流人工交互挂起）在智能体会话语义下不可恢复，按失败终态处置；
        - E1 token 流式/E4 审批/预算分层不涉及（无模型调用、无工具执行器）。
        """
        from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
        from app.modules.workflow.service.workflow_service import WorkflowInstanceService

        caller = _SimpleUser(job["user"])
        try:
            definition = db.get(WorkflowDefinition, payload.get("workflow_definition_id") or 0)
            if (
                definition is None
                or definition.delete_time is not None
                or not definition.is_active
                or definition.current_version_id is None
            ):
                raise RuntimeError("绑定的工作流不存在、已停用或未发布（实时校验，D14）")

            service = WorkflowInstanceService(db)
            instance = service.start_instance(definition.id, {"question": job["question"]}, current_user=caller)
            trace.workflow_instance_id = instance.id
            db.add(trace)
            db.commit()

            terminal = {"success", "failed", "cancelled"}
            deadline_notified = False
            while True:
                if is_cancel_requested(handle.trace_token, handle):
                    try:
                        service.cancel_instance(instance.id, current_user=caller)
                    except HTTPException:
                        pass  # 实例已终态（竞态窗口）——以 DB 状态收尾
                    self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_CANCELLED, "已请求取消")
                    handle.close("cancelled", {"status": AGENT_RUN_CANCELLED, "message": "运行已取消"})
                    return
                if handle.deadline.expired():
                    if not deadline_notified:  # 只取消一次；等实例落终态（revoke 强制后背）
                        deadline_notified = True
                        try:
                            service.cancel_instance(instance.id, current_user=caller)
                        except HTTPException:
                            pass
                    self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_TIMED_OUT, "运行超时")
                    handle.close("timed_out", {"status": AGENT_RUN_TIMED_OUT, "message": "运行超时"})
                    return
                db.expire(instance)
                current = db.get(WorkflowInstance, instance.id)
                if current is None:
                    raise RuntimeError("工作流实例丢失")
                if current.status in terminal:
                    instance = current
                    break
                time.sleep(0.5)

            if instance.status == "success":
                answer = self._workflow_output_answer(instance)
                db.add(
                    AgentMessage(
                        session_id=session_row.id,
                        role="assistant",
                        content=answer,
                    )
                )
                self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_COMPLETED, None)
                handle.close(
                    "final",
                    {
                        "status": AGENT_RUN_COMPLETED,
                        "answer": answer,
                        "modelCalls": 0,
                        "toolRounds": 0,
                        "workflowInstanceId": instance.id,
                    },
                )
            elif instance.status == "cancelled":
                self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_CANCELLED, "工作流已取消")
                handle.close("cancelled", {"status": AGENT_RUN_CANCELLED, "message": "运行已取消"})
            else:  # failed / paused 及其他未知非终态值一律按失败处置
                error_text = instance.error_message or (
                    "工作流进入人工交互挂起，智能体会话模式不支持（请直接在工作流模块恢复）"
                    if instance.status == "paused"
                    else "工作流执行失败"
                )
                self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_FAILED, error_text)
                handle.close("error", {"status": AGENT_RUN_FAILED, "message": error_text[:300]})
        except Exception as exc:  # noqa: BLE001 —— 终态机同构：致命错误 failed（对照 graph 分支）
            logger.exception("agent 编排运行失败 trace=%s", trace.id)
            if is_cancel_requested(handle.trace_token, handle):
                self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_CANCELLED, "已请求取消")
                handle.close("cancelled", {"status": AGENT_RUN_CANCELLED, "message": "运行已取消"})
            else:
                self._finish_workflow_run(db, job, trace, session_row, started, AGENT_RUN_FAILED, str(exc))
                handle.close("error", {"status": AGENT_RUN_FAILED, "message": str(exc)[:300]})

    @staticmethod
    def _workflow_output_answer(instance: Any) -> str:
        """从终态实例 state_data 提取 end 节点的 workflow_output 规整为回复文本。"""
        import json as _json

        try:
            output = (_json.loads(instance.state_data or "{}") or {}).get("workflow_output")
        except ValueError:
            output = None
        if output is None:
            return "（工作流执行完成，但未产出输出——请检查结束节点的输出配置）"
        if isinstance(output, str):
            return output
        return _json.dumps(output, ensure_ascii=False, indent=2)

    def _finish_workflow_run(
        self,
        db: Any,
        job: dict,
        trace: AgentRunTrace,
        session_row: AgentSession,
        started: float,
        status: str,
        error: str | None,
    ) -> None:
        """编排模式终态落库：assistant 消息由调用方按需写（成功路径），此处只收口 trace/会话。"""
        with timed(
            "worker.finish_commit",
            level=logging.INFO,
            slow="phase",
            trace_token=job["handle"].trace_token,
            message="agent 编排终态落库耗时",
        ):
            self._finish_workflow_run_inner(db, job, trace, session_row, started, status, error)

    def _finish_workflow_run_inner(
        self,
        db: Any,
        job: dict,
        trace: AgentRunTrace,
        session_row: AgentSession,
        started: float,
        status: str,
        error: str | None,
    ) -> None:
        trace.status = status
        trace.error = error
        trace.model_calls = 0  # 无模型调用（工作流内部计费归 workflow 模块）
        trace.tool_rounds = 0
        trace.tool_calls = 0
        trace.duration_ms = int((time.monotonic() - started) * 1000)
        db.add(trace)
        session_row.last_message_at = _dt.now(UTC)
        db.add(session_row)
        db.commit()

    def _suspend_run(
        self,
        db: Any,
        job: dict,
        trace: AgentRunTrace,
        session_row: AgentSession,
        handle: RunHandle,
        susp: Any,
        started: float,
    ) -> None:
        """E4 挂起处置：审批行（pending 组）+ 挂起 AI 消息（组重建锚点）+ trace=waiting_approval。

        - 审批占位永不入消息：挂起只落 AI 消息（组重建锚点：meta.toolCalls 是普通调用的
          args 唯一持久化处），不产生任何 tool 结果（恢复时原子补齐）；恢复终态落库时
          首条 AI 已在库——_finish_resume 剔除防重复；
        - tool_round 取「即将进入的轮序号」（组合唯一键的轮维度）；
        - execution_ms 累积挂起前执行时长（D27：duration 不含审批等待）；
        - error 备注保留 token（stopStream/resume 仍按 token 定位）。
        """
        from app.modules.agent.model.agent import AgentToolApproval
        from app.modules.agent.service import approval_service

        ai_message: AIMessage = susp.ai_message
        calls = [dict(c) for c in (ai_message.tool_calls or [])]
        last_round = db.exec(
            select(AgentToolApproval.tool_round)
            .where(AgentToolApproval.trace_id == trace.id)
            .order_by(AgentToolApproval.tool_round.desc())  # type: ignore[attr-defined]
            .limit(1)
        ).first()
        tool_round = int(last_round or 0) + 1  # 组合唯一键的轮维度（跨挂起递增，异常路径 state 不可得）
        group_id = approval_service.create_group(
            db,
            trace_id=trace.id,
            session_id=session_row.id,
            tool_round=tool_round,
            ai_message=ai_message,
            snapshot_id=trace.snapshot_id,
            requested_by=job["user"]["id"],
        )
        db.add(
            AgentMessage(
                session_id=session_row.id,
                role="assistant",
                content=ai_message.content if isinstance(ai_message.content, str) else str(ai_message.content),
                meta=json.dumps(
                    {"toolCalls": calls, "approvalGroupId": group_id, "toolRound": tool_round},
                    ensure_ascii=False,
                ),
            )
        )
        trace.status = AGENT_RUN_WAITING_APPROVAL
        trace.execution_ms = int(trace.execution_ms or 0) + int((time.monotonic() - started) * 1000)
        db.add(trace)
        session_row.last_message_at = _dt.now(UTC)
        db.add(session_row)
        db.commit()
        handle.close_suspended(
            {
                "traceId": trace.id,
                "traceToken": handle.trace_token,
                "groupId": group_id,
                "toolRound": tool_round,
                "message": "本轮包含需要人工审批的工具调用，已挂起等待审批",
                "approvals": [
                    {
                        "toolCallId": c.get("id") or "",
                        "toolName": c.get("name") or "",
                        "needsApproval": approval_service.approval_required_for(c.get("name") or ""),
                    }
                    for c in calls
                ],
            }
        )
        logger.info("agent run 挂起待审批 trace=%s group=%s round=%s", trace.id, group_id, tool_round)

    # --- E4 恢复执行（审批决定/过期后触发；D27 三概念分离之三）---

    def resume_trace(self, trace_id: int) -> dict:
        """恢复入口：gate（组内全终局）→ claim trace waiting→running（原子防双 spawn）→ 重取锁 → spawn。

        恢复使用挂起时快照（D13），渠道/窗口/启用等实时约束在载荷重建与执行链中照常校验。
        """
        import threading as _threading
        import uuid as _uuid

        from sqlalchemy import update

        from app.modules.agent.model.agent import AgentProfile
        from app.modules.agent.service import approval_service

        trace = self.session.get(AgentRunTrace, trace_id)
        if trace is None or trace.delete_time is not None:
            raise HTTPException(status_code=404, detail="运行轨迹不存在")
        # claim-first：状态判定交给条件更新 rowcount（同 Session 连调时 identity map 可能
        # 缓存挂起前的旧 status——工作线程写入对本 Session 不可见，读判定会误报非挂起）
        trace_token = _find_token_in_trace(trace.error) or _uuid.uuid4().hex
        claimed = self.session.execute(
            update(AgentRunTrace)
            .where(AgentRunTrace.id == trace_id, AgentRunTrace.status == AGENT_RUN_WAITING_APPROVAL)
            .values(status=AGENT_RUN_RUNNING)
        )
        self.session.commit()
        if not claimed.rowcount:  # 非 waiting 或已被其他执行方认领（A34 多 worker 安全）
            self.session.expire(trace)
            return {"resumed": False, "reason": f"trace 状态为 {trace.status}，非挂起待恢复或已被认领"}
        live = approval_service.suspended_group_of(self.session, trace_id)
        if live is None:
            self._revert_claim(trace_id)
            return {"resumed": False, "reason": "无待恢复的审批组"}
        group_id, _rows = live
        group_id, _rows = live
        if not approval_service.gate_satisfied(self.session, trace_id, group_id):
            self._revert_claim(trace_id)
            return {"resumed": False, "reason": "组内审批未全部终局（整组恢复门槛）"}
        profile = self.session.get(AgentProfile, trace.profile_id)
        if profile is None or profile.delete_time is not None:
            self._revert_claim(trace_id)
            raise HTTPException(status_code=404, detail="智能体不存在")
        payload = self._load_resume_payload(profile, trace)
        if not acquire_run_lock(trace.session_id, trace_token, int(payload.get("timeout_seconds") or 60)):
            # 锁被持有 = 有活 run 在执行（崩溃恢复路径的存活仲裁）；回滚 claim 保持可重试
            self._revert_claim(trace_id)
            return {"resumed": False, "reason": "该会话有运行正在执行，稍后重试"}
        job = {
            "trace_id": trace_id,
            "session_id": trace.session_id,
            "group_id": group_id,
            "run_mode": trace.run_mode,
            "engine": self.session.get_bind(),
            "user": {"id": trace.user_id, "name": "", "is_super_admin": False},
            "payload": payload,
            "trace_token": trace_token,
        }
        worker = _threading.Thread(
            target=self._execute_resume, args=(job,), name=f"agent-resume-{trace_token[:8]}", daemon=True
        )
        worker.start()
        return {"resumed": True, "traceToken": trace_token, "groupId": group_id}

    def _revert_claim(self, trace_id: int) -> None:
        """claim 回滚（gate/锁未过）：running → waiting（条件更新，幂等可重试）。"""
        from sqlalchemy import update as _update

        self.session.execute(
            _update(AgentRunTrace)
            .where(AgentRunTrace.id == trace_id, AgentRunTrace.status == AGENT_RUN_RUNNING)
            .values(status=AGENT_RUN_WAITING_APPROVAL)
        )
        self.session.commit()

    def _load_resume_payload(self, profile: Any, trace: AgentRunTrace) -> dict:
        """恢复载荷：published 用挂起时快照 id（非 current，D13）；draft 用当前草稿（调试语义）。"""
        if trace.run_mode != AGENT_RUN_MODE_PUBLISHED:
            return self._load_payload(profile, AGENT_RUN_MODE_DRAFT)
        snapshot = self.session.get(AgentProfileSnapshot, trace.snapshot_id)
        if snapshot is None or snapshot.delete_time is not None:
            raise HTTPException(status_code=409, detail="挂起时的发布快照已不存在，无法恢复执行")
        return self._payload_from_snapshot(profile, json.loads(snapshot.snapshot_json or "{}"))

    def _execute_resume(self, job: dict) -> None:
        """恢复线程：按终局处置审批组 → graph 从工具结果段续跑 → 原终态机收尾。

        逐 call 处置（二批 3.5 整组恢复门槛）：
        - approved 且组内无 blocker：args_hash 比对（A14）→ executing 租约 claim → 完整校验链执行
          （复用 ToolExecutor 单链：契约/绑定/启停/level/参数全查）→ succeeded/failed；
        - rejected/expired/cancelled：明确结果 ToolMessage，不执行；blocker 下的 approved 同样不执行
          （收口为 cancelled 防悬挂），普通调用标记「因审批组挂起未执行」；
        - 组内无 blocker 时普通调用照常执行。
        消息结构：state = [挂起 AI, *组结果]，挂起 AI 随终态一次性落库（发起段已落 user 消息）。
        """
        from sqlmodel import Session as SqlSession

        from app.core.database import engine as app_engine
        from app.modules.agent.model.agent import AGENT_APPROVAL_EXPIRED
        from app.modules.agent.service import approval_service
        from app.modules.agent.service.runtime.graph import GraphDeps, build_agent_graph
        from app.modules.agent.service.runtime.memory_service import ContextBudgetError, truncate_tool_result
        from app.modules.agent.service.runtime.model_wrapper import LoomChatModel
        from app.modules.ai.service.runtime_service import AiModelRuntimeService

        handle = RunHandle(
            trace_id=job["trace_id"],
            trace_token=job["trace_token"],
            session_id=job["session_id"],
            deadline=RunDeadline(int(job["payload"].get("timeout_seconds") or 60)),
        )
        _register_handle(handle)
        job["handle"] = handle  # _finish_run_inner 消费 job["handle"]（trace_token 语义借用注释统一）
        payload = job["payload"]
        started = time.monotonic()

        def should_cancel() -> bool:
            return is_cancel_requested(handle.trace_token, handle) or handle.deadline.expired()

        try:
            run_engine = job.get("engine") or app_engine
            with SqlSession(run_engine) as db:
                trace: AgentRunTrace = db.get(AgentRunTrace, job["trace_id"])
                session_row: AgentSession = db.get(AgentSession, job["session_id"])
                try:
                    runtime = AiModelRuntimeService(db)
                    budget = RunBudget(max_tool_rounds=int(payload["max_tool_rounds"]))
                    budget.model_calls = 1  # 挂起前产生 tool_calls 的那次模型调用已消耗
                    budget.tool_rounds = 0  # 挂起轮未执行（预检先于计数）；组处置随本轮执行计
                    job["_budget"] = budget
                    model = LoomChatModel(
                        model_profile_code=payload.get("model_profile_code") or "",
                        temperature=payload["temperature"],
                        max_tokens=payload["max_tokens"],
                        profile_source=job["run_mode"],
                        timeout_seconds=handle.deadline.per_request_timeout(payload["timeout_seconds"]),
                        min_context_window=payload.get("context_window_min"),
                    )
                    model._runtime_service = runtime  # noqa: SLF001
                    model._caller = _SimpleUser(job["user"])  # noqa: SLF001
                    model._task_id = trace.id  # noqa: SLF001

                    tool_ctx = _ToolCtx(
                        db=db,
                        user_id=job["user"]["id"],
                        user_name=job["user"].get("name") or "",
                        is_super_admin=bool(job["user"].get("is_super_admin")),
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

                    def validate_guardrails(messages):
                        from langchain_core.messages import SystemMessage as _Sys

                        from app.modules.agent.service.runtime import prompt_render

                        if (
                            not messages
                            or not isinstance(messages[0], _Sys)
                            or not prompt_render.is_guardrails_intact(messages[0].content)
                        ):
                            raise RuntimeError("护栏完整性校验失败（fail-close）")

                    from app.modules.agent.service.runtime import prompt_render

                    system_message = prompt_render.render(payload["system_prompt"], {"user_name": ""})
                    deps = GraphDeps(
                        model=model,
                        tool_executor=executor,
                        budget=budget,
                        system_message=system_message,
                        tool_schema_tokens=_estimate_schema_tokens(payload),
                        max_tool_rounds=int(payload["max_tool_rounds"]),
                        context_token_budget=int(payload.get("context_token_budget") or 0) or None,
                        stream_answer=False,  # 恢复轮非 SSE 直连，最终答案整段下发
                        guardrails_validator=validate_guardrails,
                        on_event=handle.emit,
                        should_cancel=should_cancel,
                        trace_token=handle.trace_token,
                    )
                    graph = build_agent_graph(deps)

                    group_id = job["group_id"]
                    rows = {r.tool_call_id: r for r in approval_service.group_rows(db, trace.id, group_id)}
                    ai_row, calls = _suspended_ai_of(db, session_row.id, group_id)
                    if ai_row is None:
                        raise RuntimeError("挂起消息丢失，无法恢复执行")
                    blocker = any(r.status in ("rejected", AGENT_APPROVAL_EXPIRED) for r in rows.values())
                    tool_msgs = []
                    for call in calls:
                        cid = call.get("id") or ""
                        name = call.get("name") or ""
                        args = call.get("args") or {}
                        row = rows.get(cid)
                        if row is not None and row.status == "approved" and not blocker:
                            if approval_service.args_hash_of(args) != row.args_hash:
                                approval_service.abort_approved(
                                    db, approval_id=row.id, reason="args_hash 漂移，拒绝执行"
                                )
                                tool_msgs.append(
                                    _tool_msg(cid, name, "审批锚定的参数已发生变化，拒绝执行（args_hash 校验失败）")
                                )
                                continue
                            if not approval_service.claim_for_execution(db, approval_id=row.id):
                                tool_msgs.append(_tool_msg(cid, name, "该审批已被其他流程处理"))
                                continue
                            outcome = executor._execute_single(cid, name, args)  # noqa: SLF001 —— 审批执行链复用
                            approval_service.finish_execution(
                                db,
                                approval_id=row.id,
                                success=outcome.success,
                                result_summary=truncate_tool_result(outcome.content),
                            )
                            tool_msgs.append(_tool_msg(cid, name, outcome.content))
                            continue
                        if row is not None:
                            reason = {
                                "rejected": "该工具调用审批未通过",
                                AGENT_APPROVAL_EXPIRED: "该工具调用审批已过期",
                            }.get(row.status, "同组存在被拒绝/过期的审批调用，本调用未执行")
                            if row.status == "approved":
                                approval_service.abort_approved(
                                    db, approval_id=row.id, reason="审批组含拒绝/过期调用，未执行"
                                )
                            tool_msgs.append(_tool_msg(cid, name, reason))
                            continue
                        if blocker:  # 普通 call：组内有拒绝/过期 → 一律不执行（保守，模型决定后续）
                            tool_msgs.append(_tool_msg(cid, name, "因审批组挂起未执行（组内存在被拒绝/过期的审批）"))
                            continue
                        outcome = executor._execute_single(cid, name, args)  # noqa: SLF001
                        tool_msgs.append(_tool_msg(cid, name, outcome.content))

                    # 组处置不占 execute_tools 轮额度（非节点路径；恢复后新轮由节点正常累计）
                    state = graph.invoke(
                        {
                            "messages": [
                                AIMessage(content=ai_row.content or "", tool_calls=calls),
                                *tool_msgs,
                            ],
                            "model_calls": 1,
                            "tool_rounds": 0,
                        }
                    )
                    if is_cancel_requested(handle.trace_token, handle):
                        self._finish_resume(db, job, state, AGENT_RUN_CANCELLED, started, "已请求取消")
                        handle.close("cancelled", {"message": "运行已取消"})
                    elif handle.deadline.expired():
                        self._finish_resume(db, job, state, AGENT_RUN_TIMED_OUT, started, "运行超时")
                        handle.close("timed_out", {"message": "运行超时"})
                    else:
                        self._finish_resume(db, job, state, AGENT_RUN_COMPLETED, started, None)
                        handle.close("final", self._final_payload(state, AGENT_RUN_COMPLETED))
                except ContextBudgetError as exc:
                    self._finish_resume(db, job, None, AGENT_RUN_FAILED, started, f"上下文预算：{exc}")
                    handle.close("error", {"message": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("agent 恢复执行失败 trace=%s", job["trace_id"])
                    if is_cancel_requested(handle.trace_token, handle):
                        self._finish_resume(db, job, None, AGENT_RUN_CANCELLED, started, "已请求取消")
                        handle.close("cancelled", {"message": "运行已取消"})
                    else:
                        self._finish_resume(db, job, None, AGENT_RUN_FAILED, started, str(exc))
                        handle.close("error", {"message": str(exc)[:300]})
                finally:
                    release_run_lock(job["session_id"], handle.trace_token)
        except BaseException as exc:  # noqa: BLE001
            logger.exception("agent 恢复执行兜底 trace=%s", job.get("trace_id"))
            try:
                release_run_lock(job["session_id"], handle.trace_token)
            except Exception:  # noqa: BLE001
                logger.exception("agent 恢复锁兜底释放失败 token=%s", handle.trace_token)
            handle.close("error", {"message": f"恢复执行异常终止：{str(exc)[:200]}"})

    def _finish_resume(
        self, db: Any, job: dict, state: dict | None, status: str, started: float, error: str | None
    ) -> None:
        """恢复终态：复用 _finish_run_inner + duration = execution_ms + 恢复段。

        挂起 AI 消息已在挂起时落库（组重建锚点）——state 首条 AI 剔除防重复落库。
        """
        if state is not None:
            messages = list(state.get("messages") or [])
            if messages and isinstance(messages[0], AIMessage):
                state = {**state, "messages": messages[1:]}
        self._finish_run_inner(db, job, state, status, started, error)

    def _finish_run(
        self, db: Any, job: dict, state: dict | None, status: str, started: float, error: str | None
    ) -> None:
        """终态落库：trace 计数/状态 + assistant/tool 消息入库 + ⑦ 同构处置兜底。"""
        with timed(
            "worker.finish_commit",
            level=logging.INFO,
            slow="phase",
            trace_token=job["handle"].trace_token,
            message="agent 终态落库耗时",
        ):
            self._finish_run_inner(db, job, state, status, started, error)

    def _finish_run_inner(
        self, db: Any, job: dict, state: dict | None, status: str, started: float, error: str | None
    ) -> None:
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
            # token 明细（列已存在，此前从未写入——排查渠道耗时/计费需要）
            trace.prompt_tokens = budget.prompt_tokens
            trace.completion_tokens = budget.completion_tokens
        elif error is not None and is_cancel_requested(handle.trace_token, handle):
            # 图未产出（异常终止）：⑦ 同构处置兜底由消息侧原子单元规则承担（无本轮 tool_calls 落库）
            pass
        trace.status = status
        trace.error = error
        # duration 不含审批等待（D27）：execution_ms 为挂起前累计，普通 run 恒 0（公式退化兼容）
        trace.duration_ms = int(trace.execution_ms or 0) + int((time.monotonic() - started) * 1000)
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


# --- 附件（走查反馈：图片走视觉通道，文本文件解码注入）---

_ATTACHMENT_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_ATTACHMENT_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "text/html",
    "text/xml",
}
_ATTACHMENT_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".sql",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
}
_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024  # 对齐 ai 对话测试页前端口径（chat-images.ts）
_ATTACHMENT_TEXT_TRUNCATE = 8000


def _attachment_kind(mime: str | None, filename: str | None) -> str | None:
    """附件归类：image（视觉）/ text（解码注入）/ None（不支持）。mime 缺失按扩展名兜底。"""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime in _ATTACHMENT_IMAGE_MIMES:
        return "image"
    if mime in _ATTACHMENT_TEXT_MIMES:
        return "text"
    ext = ("." + (filename or "").rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if ext in _ATTACHMENT_TEXT_EXTENSIONS:
        return "text"
    return None


def _validate_attachments(session: Any, ids: list[int], user: Any) -> list[dict]:
    """发起线程同步校验（SSE 建流前 400/403/404，好于流中 error 帧）；返回 meta 供落库。"""
    from app.modules.media.model.media import MediaAsset

    metas: list[dict] = []
    for aid in ids:
        row = session.get(MediaAsset, aid)
        if row is None or row.delete_time is not None:
            raise HTTPException(status_code=404, detail=f"附件不存在（id={aid}）")
        if row.created_by not in (None, user.id) and not getattr(user, "is_super_admin", False):
            raise HTTPException(status_code=403, detail=f"附件不可访问（id={aid}）")
        kind = _attachment_kind(row.mime_type, row.file_name)
        if kind is None:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的附件类型：{row.file_name or row.mime_type}（支持图片 png/jpeg/webp/gif 与文本类文件）",
            )
        if (row.size_bytes or 0) > _ATTACHMENT_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"附件过大：{row.file_name}（上限 5MB）")
        metas.append(
            {
                "id": row.id,
                "name": row.file_name or "",
                "mime": row.mime_type or "",
                "size": row.size_bytes or 0,
                "url": row.storage_url or "",
                "kind": kind,
            }
        )
    return metas


def _build_attachment_parts(metas: list[dict]) -> list[dict]:
    """工作线程读文件组装多模态 content parts。data URI 是唯一畅通形态（SSRF 防御拒
    /uploads 回环 URL，见 ai chat-images.ts 头注）；读取失败的附件降级为提示文本不炸 run。"""
    import base64

    from app.framework.storage import StorageService

    parts: list[dict] = []
    for meta in metas:
        try:
            content = StorageService.get_instance().read(meta["url"]) if meta.get("url") else b""
            if not content:
                raise ValueError("附件内容为空")
            if meta["kind"] == "image":
                mime = meta["mime"] or "image/png"
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(content).decode()}"},
                    }
                )
            else:
                text = content.decode("utf-8", errors="replace")
                if len(text) > _ATTACHMENT_TEXT_TRUNCATE:
                    text = text[:_ATTACHMENT_TEXT_TRUNCATE] + f"…（已截断，原文 {len(text)} 字符）"
                parts.append({"type": "text", "text": f"[附件文件 {meta['name']}]\n{text}"})
        except Exception:
            logger.warning("附件读取失败，降级为提示文本 meta=%s", meta, exc_info=True)
            parts.append({"type": "text", "text": f"[附件文件 {meta['name']} 读取失败，无法提供其内容]"})
    return parts


def _build_initial_content(question: str, parts: list[dict]) -> Any:
    """初始用户消息 content：无附件维持纯 str（零变化）；有附件组多模态数组。"""
    if not parts:
        return question
    content: list[dict] = []
    if question.strip():
        content.append({"type": "text", "text": question})
    content.extend(parts)
    return content


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


# --- E4 恢复辅助 ---


def _estimate_schema_tokens(payload: dict) -> int:
    """工具 schema token 估算（_execute_run / _execute_resume 共用口径）。"""
    from app.modules.agent.service.runtime.memory_service import estimate_tokens

    return estimate_tokens(json.dumps(list(payload["snapshot_tools"].values()), ensure_ascii=False))


def _suspended_ai_of(db: Any, session_id: int, group_id: str) -> tuple[Any | None, list[dict]]:
    """按组 id 找挂起 AI 消息（组重建锚点），返回 (row, tool_calls)。"""
    rows = db.exec(
        select(AgentMessage).where(
            AgentMessage.session_id == session_id,
            AgentMessage.role == "assistant",
            AgentMessage.delete_time == None,  # noqa: E711
        )
    ).all()
    for row in rows:
        if not row.meta:
            continue
        try:
            meta = json.loads(row.meta)
        except ValueError:
            continue
        if meta.get("approvalGroupId") == group_id:
            return row, list(meta.get("toolCalls") or [])
    return None, []


def _tool_msg(call_id: str, name: str, content: str) -> _ToolMessage:
    """组处置的权威 ToolMessage（每 tool_call_id 恰一条，审批占位永不入消息）。"""
    return _ToolMessage(tool_call_id=call_id, name=name, content=content)
