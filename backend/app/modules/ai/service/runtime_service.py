"""AI 模型统一运行时服务。"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import threading
import time
import time as time_module
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.config import settings
from app.core.logging import workflow_instance_id_ctx
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiImageRequest,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiProvider,
    AiRerankRequest,
    AiRuntimeInvocation,
    AiVideoRequest,
)
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.governance_service import (
    AiGovernanceBlocked,
    AiGovernanceService,
    AiGovernanceUnavailable,
)
from app.modules.ai.service.registry_service import AiModelRegistryService
from app.modules.ai.service.security_service import AiSecurityService
from app.modules.ai.service.stats_service import invalidate_summary_cache
from app.modules.ai.service.utils import (
    _adapter_timeout,
    _calculate_cost_micro_usd,
    _is_structured_response,
    _options_without_governance,
    _parse_content,
    _sse_event,
    _with_parsed_content,
    normalize_response_format,
    sanitize_options_for_log,
    summarize_image_result_items,
    summarize_prompt,
)
from app.modules.base.model.auth import User

logger = logging.getLogger(__name__)

# 当前请求内 fallback 降级深度：跨 _fallback/_stream_fallback 递归累加，
# 防止 fallback 链成环时 _invoke 失败→_fallback→_invoke 形成无限递归（最终 RecursionError 崩 worker）
_fallback_depth: contextvars.ContextVar[int] = contextvars.ContextVar("ai_fallback_depth", default=0)
MAX_FALLBACK_DEPTH = 5

# 流式静默心跳间隔：上游超过该时长无任何事件产出时输出 SSE 注释帧保活，
# 避免首 token 等待 / 深度思考期间被中间代理或公网网关（Cloudflare/ALB 默认空闲超时）掐断
_STREAM_HEARTBEAT_INTERVAL_SECONDS = 15.0

# 心跳/结束哨兵：仅在 _with_heartbeat 的内部队列中流转，不会进入业务事件流
_STREAM_HEARTBEAT = object()
_STREAM_DONE = object()


def _with_heartbeat(events: Iterable[dict], interval: float = _STREAM_HEARTBEAT_INTERVAL_SECONDS) -> Iterable[dict]:
    """为同步上游事件流插入心跳哨兵（静默超过 interval 秒时产出 _STREAM_HEARTBEAT）。

    同步生成器阻塞在上游 read 时控制权不回到循环体，无法自行插心跳；
    借一个 pump 线程把"等待下一条事件"转成"带超时的队列等待"。上游异常经
    队列原样透传给主迭代重新 raise，保持现有降级分支语义不变。生成器关闭
    （客户端断开）时通过 stop 事件通知 pump 退出——若其正阻塞在上游 read，
    最迟在下一条数据或 adapter 读超时后退出（daemon 线程兜底）。
    """
    events_queue: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _pump() -> None:
        try:
            for event in events:
                if stop.is_set():
                    break
                events_queue.put(event)
        except BaseException as exc:  # noqa: BLE001 - 需要把上游任意异常转交主迭代处理
            events_queue.put(exc)
        finally:
            events_queue.put(_STREAM_DONE)

    threading.Thread(target=_pump, daemon=True, name="ai-stream-heartbeat-pump").start()
    try:
        while True:
            try:
                item = events_queue.get(timeout=interval)
            except queue.Empty:
                yield _STREAM_HEARTBEAT
                continue
            if item is _STREAM_DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()


def _independent_session(request_session: Session) -> Session:
    """为流式生成器创建与请求会话同库的独立 Session。

    流式生成器由 Starlette 在 AnyIO 线程池中迭代,线程与创建请求会话的事件循环不同,
    而 SQLAlchemy Session 非线程安全(流式专项审查 P1)。这里按请求会话的 bind 另开
    会话:生产环境与请求同库,测试环境天然指向用例自身的内存库引擎(make_test_engine)。
    不能改用全局 SessionLocal——其绑定全局 engine,会写穿测试隔离。
    """
    return Session(request_session.get_bind())


def _make_absolute_url(path: str) -> str:
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
        return path
    if path.startswith("/"):
        base_url = settings.BACKEND_URL or settings.EXTERNAL_URL
        if not base_url:
            host = settings.HOST
            if host == "0.0.0.0":
                host = "127.0.0.1"
            base_url = f"http://{host}:{settings.PORT}"

        return f"{base_url.rstrip('/')}{path}"
    return path


@dataclass
class _InvocationState:
    """单次模型调用的治理/审计上下文（_invoke 与 _stream_invoke 共用前置流程）。

    `closed` 标记治理收尾（finish/block）是否已发生：流式路径的 finally 兜底
    依赖它避免双重收尾；非流式路径忽略。
    """

    provider: AiProvider
    model: AiModel
    profile: AiModelProfile
    governance: AiGovernanceService
    start: float
    invocation: AiRuntimeInvocation | None = None
    closed: bool = False

    @classmethod
    def from_resolved(cls, session: Session, resolved: dict, start: float) -> _InvocationState:
        return cls(
            provider=resolved["provider"],
            model=resolved["model"],
            profile=resolved["profile"],
            governance=AiGovernanceService(session),
            invocation=None,
            closed=False,
            start=start,
        )


class AiModelRuntimeService:
    def __init__(self, session: Session):
        self.session = session

    def _resolve_with_options(self, model_type: str, payload) -> tuple[dict, dict[str, Any]]:
        """公共前置流程：按 model_type 解析 profile，并把请求级 options 叠加在 profile 默认之上。"""
        resolved = AiModelRegistryService(self.session).resolve(
            model_type=model_type, scenario=payload.scenario, profile_code=payload.profile_code
        )
        return resolved, {**resolved["options"], **payload.options}

    def _begin_invocation(self, st: _InvocationState, user: User | None, task_id: int | None = None):
        st.invocation = st.governance.begin(
            user=user, provider=st.provider, model=st.model, profile=st.profile, task_id=task_id
        )

    def _audit_success(
        self,
        st: _InvocationState,
        usage: dict[str, Any],
        *,
        session: Session,
        user: User | None,
        cost_micro_usd: int,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理收尾（success）+ 成功审计日志，并标记 closed。"""
        st.governance.finish(
            st.invocation,
            status_value="success",
            user=user,
            provider=st.provider,
            model=st.model,
            profile=st.profile,
            usage=usage,
            cost_micro_usd=cost_micro_usd,
        )
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            "success",
            st.start,
            usage,
            user=user,
            cost_micro_usd=cost_micro_usd,
            request_id=request_id,
            options=options,
            session=session,
        )

    def _audit_failure(
        self,
        st: _InvocationState,
        status_value: str,
        usage: dict[str, Any],
        detail: str | None,
        *,
        session: Session,
        user: User | None,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理收尾（指定状态，cost=0）+ 失败审计日志，并标记 closed。"""
        st.governance.finish(
            st.invocation,
            status_value=status_value,
            user=user,
            provider=st.provider,
            model=st.model,
            profile=st.profile,
            usage=usage,
            cost_micro_usd=0,
        )
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            status_value,
            st.start,
            usage,
            detail,
            user=user,
            request_id=request_id,
            options=options,
            session=session,
        )

    def _block_invocation(
        self,
        st: _InvocationState,
        status_value: str,
        usage: dict[str, Any],
        detail: str,
        *,
        session: Session,
        user: User | None,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理阻断（block_invocation，用于 Redis 故障 fail-closed / 规则拦截）+ 审计日志。"""
        st.governance.block_invocation(st.invocation)
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            status_value,
            st.start,
            usage,
            detail,
            user=user,
            request_id=request_id,
            options=options,
            session=session,
        )

    def chat(self, payload: AiChatRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        AiSecurityService.check_input_safety(payload.messages)
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        return self._invoke(
            resolved,
            "chat",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
            skip_masking=payload.skip_masking,
            messages=[item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages],
            options=options,
        )

    def stream_chat(self, payload: AiChatRequest, current_user: User | None = None) -> Iterable[str]:
        AiSecurityService.check_input_safety(payload.messages)
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        messages = [item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages]
        return self._stream_invoke(
            resolved,
            current_user=current_user,
            messages=messages,
            options=options,
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
        )

    def embedding(
        self, payload: AiEmbeddingRequest, current_user: User | None = None, task_id: int | None = None
    ) -> dict:
        resolved, options = self._resolve_with_options("embedding", payload)
        return self._invoke(
            resolved,
            "embedding",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            input=payload.input,
            options=options,
        )

    def image(self, payload: AiImageRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        resolved, options = self._resolve_with_options("image", payload)
        if payload.image:
            image_val = payload.image
            if isinstance(image_val, str):
                image_val = _make_absolute_url(image_val)
            elif isinstance(image_val, list):
                image_val = [_make_absolute_url(url) for url in image_val]
            options["image"] = image_val
            payload.image = image_val
        logger.info(
            "AI 生图请求已解析",
            extra={
                "method": "image",
                "scenario": payload.scenario,
                "profile_code": payload.profile_code,
                "provider": resolved["provider"].code,
                "provider_adapter": resolved["provider"].adapter,
                "model": resolved["model"].code,
                "resolved_profile": resolved["profile"].code,
                "prompt": summarize_prompt(payload.prompt),
                "options": sanitize_options_for_log(options),
            },
        )
        return self._invoke(
            resolved,
            "image",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            prompt=payload.prompt,
            options=options,
        )

    def rerank(self, payload: AiRerankRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        resolved, options = self._resolve_with_options("rerank", payload)
        return self._invoke(
            resolved,
            "rerank",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            query=payload.query,
            documents=payload.documents,
            options=options,
        )

    def audio(self, payload: AiAudioRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        resolved, options = self._resolve_with_options("audio", payload)
        return self._invoke(
            resolved,
            "audio",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            input=payload.input,
            options=options,
        )

    def video(self, payload: AiVideoRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        resolved, options = self._resolve_with_options("video", payload)
        return self._invoke(
            resolved,
            "video",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            prompt=payload.prompt,
            options=options,
        )

    def _invoke(
        self,
        resolved: dict,
        method: str,
        current_user: User | None = None,
        task_id: int | None = None,
        request_options: dict[str, Any] | None = None,
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        skip_masking: bool = False,
        **kwargs: Any,
    ) -> dict:
        start = time.perf_counter()
        st = _InvocationState.from_resolved(self.session, resolved, start)
        provider, model, profile = st.provider, st.model, st.profile
        usage: dict[str, Any] = {}
        request_options = request_options or {}
        # kwargs 里的 options 优先于 payload 级 request_options（各分支共用同一口径）
        effective_options = kwargs.get("options") or request_options
        log_context = {
            "method": method,
            "provider": provider.code,
            "provider_adapter": provider.adapter,
            "model": model.code,
            "profile": profile.code,
            "scenario": profile.scenario,
        }
        try:
            self._begin_invocation(st, current_user, task_id)
            adapter = build_adapter(provider)
            if method == "image":
                logger.info(
                    "AI 生图调用开始",
                    extra={
                        **log_context,
                        "prompt": summarize_prompt(kwargs.get("prompt")),
                        "options": sanitize_options_for_log(kwargs.get("options")),
                    },
                )
            result = self._invoke_with_retry(adapter, method, profile, model.code, kwargs)
            usage = result.get("usage") or {}
            cost_micro_usd = _calculate_cost_micro_usd(model, usage)
            self._audit_success(
                st,
                usage,
                user=current_user,
                cost_micro_usd=cost_micro_usd,
                request_id=result.get("requestId"),
                options=effective_options,
                session=self.session,
            )
            if method == "image":
                logger.info(
                    "AI 生图调用成功",
                    extra={
                        **log_context,
                        "latency_ms": int((time.perf_counter() - start) * 1000),
                        "upstream_request_id": result.get("requestId"),
                        "usage": usage,
                        "image_count": len(result.get("data") or []),
                        "images": summarize_image_result_items(result.get("data")),
                    },
                )
            if method == "chat" and _is_structured_response(structured_response):
                result = _with_parsed_content(result)

            # 对聊天结果进行 PII 脱敏（跳过结构化数据，避免破坏 JSON，或配置跳过）
            if (
                method == "chat"
                and "content" in result
                and result["content"]
                and not skip_masking
                and not _is_structured_response(structured_response)
            ):
                result["content"] = AiSecurityService.mask_sensitive_output(result["content"])

            return {"success": True, "provider": provider.code, "model": model.code, "profile": profile.code, **result}
        except AiGovernanceUnavailable as exc:
            # Redis 故障导致 cost 类并发规则无法判定：fail-closed 返回 503（P0-17）
            self._block_invocation(
                st, "unavailable", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except AiGovernanceBlocked as exc:
            self._block_invocation(
                st, "blocked", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
        except UnsupportedCapabilityError as exc:
            self._audit_failure(
                st, "unsupported", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except Exception as exc:
            self._audit_failure(
                st, "error", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            # 所有方法失败统一打一条结构化 ERROR（含完整 traceback）；
            # request_id 由 Formatter 自动从 contextvar 注入，无需在此重复
            logger.error(
                "AI 模型调用失败",
                extra={
                    **log_context,
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "prompt": summarize_prompt(kwargs.get("prompt")),
                    "options": sanitize_options_for_log(kwargs.get("options")),
                    "fallback_profile_id": profile.fallback_profile_id,
                },
                exc_info=exc,
            )
            fallback = self._fallback(
                profile,
                method,
                kwargs,
                request_options,
                structured_response,
                response_format_overridden,
                current_user=current_user,
                task_id=task_id,
            )
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"模型调用失败: {exc}") from exc

    def _invoke_with_retry(
        self, adapter, method: str, profile: AiModelProfile, model_code: str, kwargs: dict[str, Any]
    ) -> dict:
        attempts = max(0, int(profile.retry_count or 0)) + 1
        retry_delay = max(0, int(profile.retry_delay_seconds or 0))
        last_exc: Exception | None = None
        for index in range(attempts):
            try:
                call_kwargs = dict(kwargs)
                effective_timeout = (call_kwargs.get("options") or {}).get("timeout") or profile.timeout
                call_kwargs["options"] = _options_without_governance(call_kwargs.get("options") or {})
                with _adapter_timeout(adapter, effective_timeout):
                    return getattr(adapter, method)(model=model_code, **call_kwargs)
            except UnsupportedCapabilityError:
                raise
            except Exception as exc:
                last_exc = exc
                if index >= attempts - 1:
                    break
                if retry_delay:
                    time_module.sleep(retry_delay)
        raise last_exc or RuntimeError("模型调用失败")

    def _resolve_chat(self, payload: AiChatRequest) -> tuple[dict, dict[str, Any], bool]:
        resolved = AiModelRegistryService(self.session).resolve(
            model_type="chat", scenario=payload.scenario, profile_code=payload.profile_code
        )
        options = {**resolved["options"], **payload.options}
        response_format_overridden = payload.response_format is not None
        request_response_format = (
            normalize_response_format(payload.response_format) if payload.response_format else None
        )
        if request_response_format:
            options["response_format"] = request_response_format
        elif response_format_overridden:
            options.pop("response_format", None)
        return resolved, options, response_format_overridden

    def _stream_invoke(
        self,
        resolved: dict,
        *,
        current_user: User | None = None,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        request_options: dict[str, Any] | None = None,
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        skip_masking: bool = False,
    ) -> Iterable[str]:
        start = time.perf_counter()
        # 流式生成器由 Starlette 在 AnyIO 线程池中迭代，与创建请求会话的事件循环线程不同，
        # SQLAlchemy Session 非线程安全：改用同库独立会话，随生成器 finally 关闭
        session = _independent_session(self.session)
        st = _InvocationState.from_resolved(session, resolved, start)
        provider, model, profile = st.provider, st.model, st.profile
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        request_id: str | None = None
        emitted_delta = False
        done_sent = False
        request_options = request_options or {}

        try:
            self._begin_invocation(st, current_user)
            yield _sse_event(
                {"event": "start", "provider": provider.code, "model": model.code, "profile": profile.code}
            )
            adapter = build_adapter(provider)
            with _adapter_timeout(adapter, profile.timeout):
                stream_events = _with_heartbeat(
                    adapter.stream_chat(
                        model=model.code, messages=messages, options=_options_without_governance(options)
                    )
                )
                for event in stream_events:
                    if event is _STREAM_HEARTBEAT:
                        # SSE 注释帧保活：前端 parseSse 跳过 ':' 行，不影响业务事件解析
                        yield ": heartbeat\n\n"
                        continue
                    request_id = event.get("requestId") or request_id
                    usage = event.get("usage") or usage
                    event_name = event.get("event")
                    if event_name in {"delta", "thinking_delta", "tool_delta"}:
                        text = event.get("content") or ""
                        if event_name == "delta":
                            content_parts.append(text)
                            emitted_delta = True
                        # 流式输出阶段跳过脱敏（保证实时性和不破坏思考片段），仅在 done 中做全量脱敏
                        yield _sse_event({"event": event_name, "content": text})
                        continue
                    if event_name == "error":
                        message = event.get("content") or "模型流式调用失败"
                        self._audit_failure(
                            st,
                            "error",
                            usage,
                            str(message),
                            user=current_user,
                            request_id=request_id,
                            session=session,
                        )
                        yield _sse_event({"event": "error", "message": str(message), "status": 400})
                        return
                    if event_name == "done":
                        if event.get("usage"):
                            usage = event.get("usage") or usage
                        if event.get("requestId"):
                            request_id = event.get("requestId")
            content = "".join(content_parts)
            # 对流式完成后的完整内容进行脱敏（跳过结构化数据，或配置跳过）
            if not skip_masking and not _is_structured_response(structured_response):
                content = AiSecurityService.mask_sensitive_output(content)
            done_payload = {"event": "done", "content": content, "usage": usage or {}}
            if _is_structured_response(structured_response):
                parsed = _parse_content(content)
                done_payload.update(parsed)
            cost_micro_usd = _calculate_cost_micro_usd(model, usage)
            self._audit_success(
                st,
                usage,
                user=current_user,
                cost_micro_usd=cost_micro_usd,
                request_id=request_id,
                options=request_options,
                session=session,
            )
            done_sent = True
            yield _sse_event(done_payload)
        except AiGovernanceUnavailable as exc:
            # Redis 故障导致 cost 类并发规则无法判定：fail-closed 返回 503（P0-17）
            self._block_invocation(
                st,
                "unavailable",
                usage,
                str(exc),
                user=current_user,
                request_id=request_id,
                options=request_options,
                session=session,
            )
            yield _sse_event({"event": "error", "message": str(exc), "status": 503})
        except AiGovernanceBlocked as exc:
            self._block_invocation(
                st,
                "blocked",
                usage,
                str(exc),
                user=current_user,
                request_id=request_id,
                options=request_options,
                session=session,
            )
            yield _sse_event({"event": "error", "message": str(exc), "status": 429})
        except UnsupportedCapabilityError as exc:
            self._audit_failure(
                st,
                "unsupported",
                usage,
                str(exc),
                user=current_user,
                request_id=request_id,
                options=request_options,
                session=session,
            )
            yield _sse_event({"event": "error", "message": str(exc), "status": 501})
        except Exception as exc:
            logger.error(
                "AI 模型调用失败",
                extra={
                    "method": "stream_chat",
                    "provider": provider.code,
                    "provider_adapter": provider.adapter,
                    "model": model.code,
                    "profile": profile.code,
                    "scenario": profile.scenario,
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "request_id": request_id,
                    "fallback_profile_id": profile.fallback_profile_id,
                },
                exc_info=exc,
            )
            if not emitted_delta:
                fallback = self._stream_fallback(
                    profile,
                    messages,
                    request_options,
                    structured_response,
                    response_format_overridden,
                    current_user=current_user,
                    session=session,
                )
                if fallback is not None:
                    self._audit_failure(
                        st,
                        "error",
                        usage,
                        str(exc),
                        user=current_user,
                        request_id=request_id,
                        options=request_options,
                        session=session,
                    )
                    yield from fallback
                    return
            if not done_sent:
                self._audit_failure(
                    st,
                    "error",
                    usage,
                    str(exc),
                    user=current_user,
                    request_id=request_id,
                    options=request_options,
                    session=session,
                )
                yield _sse_event({"event": "error", "message": f"模型调用失败: {exc}", "status": 400})
        finally:
            if st.invocation is not None and not st.closed:
                st.governance.finish(
                    st.invocation,
                    status_value="error",
                    user=current_user,
                    provider=provider,
                    model=model,
                    profile=profile,
                    usage=usage,
                    cost_micro_usd=0,
                )
            session.close()

    def _fallback_chain_has_cycle(self, profile: AiModelProfile, session: Session) -> bool:
        """运行期同步检测 fallback 链是否存在环或超过最大深度。

        不依赖 contextvar，对流式生成器的惰性求值同样可靠，作为保存期环校验的运行期兜底
        （堵住 TOCTOU 并发或直接改库形成的环）。返回 True 时调用方应停止降级。
        """
        visited: set[int] = set()
        cursor = profile
        depth = 0
        while cursor is not None and cursor.fallback_profile_id and depth < MAX_FALLBACK_DEPTH:
            if cursor.id in visited:
                return True
            visited.add(cursor.id)
            nxt = session.get(AiModelProfile, cursor.fallback_profile_id)
            if nxt is None:
                return False
            cursor = nxt
            depth += 1
        return cursor is not None and cursor.fallback_profile_id is not None

    def _stream_fallback(
        self,
        profile: AiModelProfile,
        messages: list[dict[str, Any]],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
        *,
        session: Session,
    ) -> Iterable[str] | None:
        if not profile.fallback_profile_id:
            return None
        # 运行期同步防环（不依赖 contextvar 的生成器时序，流式路径可靠）：堵住并发/脏数据成环导致的无限递归
        if self._fallback_chain_has_cycle(profile, session):
            logger.warning("AI 流式 fallback 链检测到环或超深，停止降级")
            return None
        # 深度兜底：fallback 链过长时停止降级
        depth = _fallback_depth.get()
        if depth >= MAX_FALLBACK_DEPTH:
            logger.warning("AI 流式 fallback 链已达最大深度 %d，停止降级", MAX_FALLBACK_DEPTH)
            return None
        token = _fallback_depth.set(depth + 1)
        try:
            fallback = session.get(AiModelProfile, profile.fallback_profile_id)
            if not fallback:
                return None
            model = session.get(AiModel, fallback.model_id)
            provider = session.get(AiProvider, model.provider_id) if model else None
            if not model or not provider or not model.is_active or not provider.is_active:
                return None
            options = {**AiModelRegistryService(session)._merge_options(model, fallback), **request_options}
            if structured_response:
                options["response_format"] = structured_response
            elif response_format_overridden:
                options.pop("response_format", None)
            return self._stream_invoke(
                {"provider": provider, "model": model, "profile": fallback, "options": options},
                current_user=current_user,
                messages=messages,
                options=options,
                request_options=request_options,
                structured_response=structured_response or options.get("response_format"),
                response_format_overridden=response_format_overridden,
            )
        finally:
            _fallback_depth.reset(token)

    def _fallback(
        self,
        profile: AiModelProfile,
        method: str,
        kwargs: dict[str, Any],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
        task_id: int | None = None,
    ) -> dict | None:
        if not profile.fallback_profile_id:
            return None
        # 运行期同步防环（不依赖 contextvar）：堵住并发/脏数据成环导致的无限递归
        if self._fallback_chain_has_cycle(profile, self.session):
            logger.warning("AI fallback 链检测到环或超深，停止降级")
            return None
        # 深度兜底：fallback 链过长时停止降级
        depth = _fallback_depth.get()
        if depth >= MAX_FALLBACK_DEPTH:
            logger.warning("AI fallback 链已达最大深度 %d，停止降级", MAX_FALLBACK_DEPTH)
            return None
        token = _fallback_depth.set(depth + 1)
        try:
            fallback = self.session.get(AiModelProfile, profile.fallback_profile_id)
            if not fallback:
                return None
            model = self.session.get(AiModel, fallback.model_id)
            provider = self.session.get(AiProvider, model.provider_id) if model else None
            if not model or not provider or not model.is_active or not provider.is_active:
                return None
            options = {**AiModelRegistryService(self.session)._merge_options(model, fallback), **request_options}
            if structured_response:
                options["response_format"] = structured_response
            elif response_format_overridden:
                options.pop("response_format", None)
            if method == "image":
                logger.warning(
                    "AI 生图触发兜底模型",
                    extra={
                        "method": method,
                        "from_profile": profile.code,
                        "to_profile": fallback.code,
                        "to_provider": provider.code,
                        "to_model": model.code,
                        "options": sanitize_options_for_log(options),
                    },
                )
            fallback_kwargs = {**kwargs, "options": options}
            return self._invoke(
                {"provider": provider, "model": model, "profile": fallback, "options": options},
                method,
                current_user=current_user,
                task_id=task_id,
                request_options=request_options,
                structured_response=structured_response or options.get("response_format"),
                response_format_overridden=response_format_overridden,
                **fallback_kwargs,
            )
        finally:
            _fallback_depth.reset(token)

    def _log_call(
        self,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
        status_value: str,
        start: float,
        usage: dict,
        error: str | None = None,
        *,
        session: Session,
        user: User | None = None,
        cost_micro_usd: int = 0,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        request_options_str: str | None = None
        if options:
            try:
                request_options_str = json.dumps(sanitize_options_for_log(options), ensure_ascii=False)
            except Exception:
                pass

        log = AiModelCallLog(
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            user_id=user.id if user else None,
            scenario=profile.scenario,
            model_type=model.model_type,
            status=status_value,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=int(usage.get("promptTokens") or 0),
            completion_tokens=int(usage.get("completionTokens") or 0),
            total_tokens=int(usage.get("totalTokens") or 0),
            cost_micro_usd=cost_micro_usd,
            currency="USD",
            error_message=(error or "")[:500] or None,
            request_id=request_id,
            workflow_instance_id=workflow_instance_id_ctx.get(),
            request_options=request_options_str,
        )
        session.add(log)
        session.commit()
        # 失效统计看板缓存：新调用日志已落库，旧聚合结果不再准确
        invalidate_summary_cache()
