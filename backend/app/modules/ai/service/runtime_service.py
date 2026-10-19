"""AI 模型统一运行时服务。

实现拆分在 ``service/runtime/`` 包（AI-013 纯搬迁，逻辑零改动）：

- common.py    共享状态（fallback 深度 contextvar / _InvocationState）
- heartbeat.py 流式心跳保活 + 流式独立会话
- input_guard.py vision 能力前置校验
- retry.py     重试分类 + 指数退避（AI-025，RetryMixin）
- audit.py     治理收尾 + 调用审计日志（_log_call 唯一写点，AuditMixin）
- fallback.py  降级链（运行期防环 + sync/stream 双路径，FallbackMixin）

``AiModelRuntimeService`` 类体（公共入口 + _invoke/_stream_invoke 两条管线）
**留在本文件**：测试套件以 ``patch("...runtime_service.build_adapter")`` /
``patch("...runtime_service.settings")`` 方式打桩（30+ 处），桩替换的是本模块
命名空间的名字，管线方法必须在本模块命名空间解析这些符号，搬走即静默失效。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiImageRequest,
    AiRerankRequest,
    AiVideoRequest,
)
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.adapters.base import AdapterInputError, UnsupportedCapabilityError
from app.modules.ai.service.errors import AiInvocationError
from app.modules.ai.service.governance_service import AiGovernanceBlocked, AiGovernanceUnavailable
from app.modules.ai.service.registry_service import AiModelRegistryService
from app.modules.ai.service.runtime.audit import AuditMixin
from app.modules.ai.service.runtime.common import (
    MAX_FALLBACK_DEPTH,
    _fallback_depth,
    _InvocationState,
)
from app.modules.ai.service.runtime.fallback import FallbackMixin
from app.modules.ai.service.runtime.heartbeat import (
    _STREAM_DONE,
    _STREAM_HEARTBEAT,
    _STREAM_HEARTBEAT_INTERVAL_SECONDS,
    _independent_session,
    _with_heartbeat,
)
from app.modules.ai.service.runtime.input_guard import _check_vision_capability
from app.modules.ai.service.runtime.retry import _RETRY_DELAY_CAP_SECONDS, RetryMixin, _is_retryable
from app.modules.ai.service.security_service import AiSecurityService
from app.modules.ai.service.utils import (
    _adapter_timeout,
    _calculate_cost_micro_usd,
    _is_structured_response,
    _options_without_governance,
    _parse_content,
    _sse_event,
    _with_parsed_content,
    make_absolute_url,
    normalize_response_format,
    sanitize_options_for_log,
    summarize_image_result_items,
    summarize_prompt,
)
from app.modules.base.model.auth import User

logger = logging.getLogger(__name__)

__all__ = [
    "AiModelRuntimeService",
    "MAX_FALLBACK_DEPTH",
    "_RETRY_DELAY_CAP_SECONDS",
    "_InvocationState",
    "_STREAM_DONE",
    "_STREAM_HEARTBEAT",
    "_STREAM_HEARTBEAT_INTERVAL_SECONDS",
    "_check_vision_capability",
    "_fallback_depth",
    "_independent_session",
    "_is_retryable",
    "_with_heartbeat",
    "make_absolute_url",
]


class AiModelRuntimeService(FallbackMixin, RetryMixin, AuditMixin):
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

    def chat(self, payload: AiChatRequest, current_user: User | None = None, task_id: int | None = None) -> dict:
        AiSecurityService.check_input_safety(payload.messages)
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        # WFI-2c：多模态输入的 vision 能力前置校验（非视觉模型绑图显式失败，
        # 不静默丢图也不把上游 400 生硬透传）
        vision_error = _check_vision_capability(resolved, payload.messages)
        if vision_error:
            return vision_error
        return self._invoke(
            resolved,
            "chat",
            current_user=current_user,
            task_id=task_id,
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
            # AI-014：客户端传 skipMasking 不得自行关闭 PII 脱敏，仅在全局开关闭合时生效
            skip_masking=settings.AI_ALLOW_SKIP_MASKING and payload.skip_masking,
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
            # 与 sync 路径同口径（AI-013 漂移症状之一）：全局开关闭合时方可跳过脱敏
            skip_masking=settings.AI_ALLOW_SKIP_MASKING and payload.skip_masking,
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
                image_val = make_absolute_url(image_val)
            elif isinstance(image_val, list):
                image_val = [make_absolute_url(url) for url in image_val]
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
        st = _InvocationState.from_resolved(self.session, resolved, start, task_id=task_id)
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
            raise AiInvocationError(str(exc), status_code=503) from exc
        except AiGovernanceBlocked as exc:
            self._block_invocation(
                st, "blocked", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise AiInvocationError(str(exc), status_code=429) from exc
        except UnsupportedCapabilityError as exc:
            self._audit_failure(
                st, "unsupported", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise AiInvocationError(str(exc), status_code=501) from exc
        except AdapterInputError as exc:
            # 适配器参数/配置错误：换模型重跑结果相同，不降级（避免二次计费）直接 4xx（AI-009）
            self._audit_failure(
                st, "error", usage, str(exc), user=current_user, options=effective_options, session=self.session
            )
            raise AiInvocationError(str(exc), status_code=400) from exc
        except Exception as exc:
            # 先回滚再审计/降级：PG 下事务 aborted 时后续 commit 会抛 PendingRollbackError（AI-006）
            self.session.rollback()
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
            raise AiInvocationError(f"模型调用失败: {exc}", status_code=400) from exc

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
            # 超时上下文产出的是本次调用专用副本（池化 adapter 不在原地改，并发不串扰）；
            # 副本被生成器闭包持有，with 退出后仍按 profile.timeout 读上游
            with _adapter_timeout(adapter, profile.timeout) as call_adapter:
                stream_events = _with_heartbeat(
                    call_adapter.stream_chat(
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
        except AdapterInputError as exc:
            # 适配器参数/配置错误：不降级，直接以 error 事件收尾（AI-009）。
            # 参数错误多数发生在首帧前，但流中途也可能抛：此时若静默返回，前端只收到
            # 半截正文、既无 done 也无 error，表现为"模型说一半卡住"（P2 静默截断）
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
                payload: dict[str, Any] = {"event": "error", "message": str(exc), "status": 400}
                if emitted_delta:
                    # 已下发部分正文：显式标记截断，与"整段失败"区分
                    payload["truncated"] = True
                yield _sse_event(payload)
        except Exception as exc:
            # 先回滚再审计/降级：PG 下事务 aborted 时后续 commit 会抛 PendingRollbackError（AI-006）
            session.rollback()
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
