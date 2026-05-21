"""AI 模型统一运行时服务。"""
from __future__ import annotations

import logging
import time
import time as time_module
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session

from app.modules.ai.model.ai import AiAudioRequest, AiChatRequest, AiEmbeddingRequest, AiImageRequest, AiModel, AiModelCallLog, AiModelProfile, AiProvider, AiRerankRequest, AiVideoRequest
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.governance_service import AiGovernanceBlocked, AiGovernanceService
from app.modules.ai.service.registry_service import AiModelRegistryService
from app.modules.ai.service.utils import _adapter_timeout, _calculate_cost_micro_usd, _is_structured_response, _options_without_governance, _parse_content, _sse_event, _with_parsed_content, normalize_response_format, sanitize_options_for_log, summarize_image_result_items, summarize_prompt
from app.modules.base.model.auth import User
from app.core.config import settings

logger = logging.getLogger(__name__)


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


class AiModelRuntimeService:
    def __init__(self, session: Session):
        self.session = session

    def chat(self, payload: AiChatRequest, current_user: User | None = None) -> dict:
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        return self._invoke(
            resolved,
            "chat",
            current_user=current_user,
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
            messages=[item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages],
            options=options,
        )

    def stream_chat(self, payload: AiChatRequest, current_user: User | None = None) -> Iterable[str]:
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

    def embedding(self, payload: AiEmbeddingRequest, current_user: User | None = None) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="embedding", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "embedding", current_user=current_user, request_options=payload.options, input=payload.input, options=options)

    def image(self, payload: AiImageRequest, current_user: User | None = None) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="image", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
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
        return self._invoke(resolved, "image", current_user=current_user, request_options=payload.options, prompt=payload.prompt, options=options)

    def rerank(self, payload: AiRerankRequest, current_user: User | None = None) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="rerank", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "rerank", current_user=current_user, request_options=payload.options, query=payload.query, documents=payload.documents, options=options)

    def audio(self, payload: AiAudioRequest, current_user: User | None = None) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="audio", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "audio", current_user=current_user, request_options=payload.options, input=payload.input, options=options)

    def video(self, payload: AiVideoRequest, current_user: User | None = None) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="video", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "video", current_user=current_user, request_options=payload.options, prompt=payload.prompt, options=options)

    def _invoke(
        self,
        resolved: dict,
        method: str,
        current_user: User | None = None,
        request_options: dict[str, Any] | None = None,
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        **kwargs: Any,
    ) -> dict:
        provider: AiProvider = resolved["provider"]
        model: AiModel = resolved["model"]
        profile: AiModelProfile = resolved["profile"]
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        request_options = request_options or {}
        governance = AiGovernanceService(self.session)
        invocation: AiRuntimeInvocation | None = None
        log_context = {
            "method": method,
            "provider": provider.code,
            "provider_adapter": provider.adapter,
            "model": model.code,
            "profile": profile.code,
            "scenario": profile.scenario,
        }
        try:
            invocation = governance.begin(user=current_user, provider=provider, model=model, profile=profile)
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
            governance.finish(invocation, status_value="success", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=cost_micro_usd)
            self._log_call(provider, model, profile, "success", start, usage, user=current_user, cost_micro_usd=cost_micro_usd, request_id=result.get("requestId"))
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
            return {"success": True, "provider": provider.code, "model": model.code, "profile": profile.code, **result}
        except AiGovernanceBlocked as exc:
            governance.block_invocation(invocation)
            self._log_call(provider, model, profile, "blocked", start, usage, str(exc), user=current_user)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
        except UnsupportedCapabilityError as exc:
            governance.finish(invocation, status_value="unsupported", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
            self._log_call(provider, model, profile, "unsupported", start, usage, str(exc), user=current_user)
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except Exception as exc:
            governance.finish(invocation, status_value="error", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
            self._log_call(provider, model, profile, "error", start, usage, str(exc), user=current_user)
            if method == "image":
                logger.error(
                    "AI 生图调用失败",
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
            fallback = self._fallback(profile, method, kwargs, request_options, structured_response, response_format_overridden, current_user=current_user)
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"模型调用失败: {exc}") from exc

    def _invoke_with_retry(self, adapter, method: str, profile: AiModelProfile, model_code: str, kwargs: dict[str, Any]) -> dict:
        attempts = max(0, int(profile.retry_count or 0)) + 1
        retry_delay = max(0, int(profile.retry_delay_seconds or 0))
        last_exc: Exception | None = None
        for index in range(attempts):
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["options"] = _options_without_governance(call_kwargs.get("options") or {})
                with _adapter_timeout(adapter, profile.timeout):
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
        resolved = AiModelRegistryService(self.session).resolve(model_type="chat", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        response_format_overridden = payload.response_format is not None
        request_response_format = normalize_response_format(payload.response_format) if payload.response_format else None
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
    ) -> Iterable[str]:
        provider: AiProvider = resolved["provider"]
        model: AiModel = resolved["model"]
        profile: AiModelProfile = resolved["profile"]
        start = time.perf_counter()
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        request_id: str | None = None
        emitted_delta = False
        done_sent = False
        request_options = request_options or {}
        governance = AiGovernanceService(self.session)
        invocation: AiRuntimeInvocation | None = None
        invocation_closed = False

        try:
            invocation = governance.begin(user=current_user, provider=provider, model=model, profile=profile)
            yield _sse_event({"event": "start", "provider": provider.code, "model": model.code, "profile": profile.code})
            adapter = build_adapter(provider)
            with _adapter_timeout(adapter, profile.timeout):
                stream_events = adapter.stream_chat(model=model.code, messages=messages, options=_options_without_governance(options))
                for event in stream_events:
                    request_id = event.get("requestId") or request_id
                    usage = event.get("usage") or usage
                    event_name = event.get("event")
                    if event_name in {"delta", "thinking_delta", "tool_delta"}:
                        text = event.get("content") or ""
                        if event_name == "delta":
                            content_parts.append(text)
                            emitted_delta = True
                        yield _sse_event({"event": event_name, "content": text})
                        continue
                    if event_name == "error":
                        message = event.get("content") or "模型流式调用失败"
                        governance.finish(invocation, status_value="error", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
                        invocation_closed = True
                        self._log_call(provider, model, profile, "error", start, usage, str(message), user=current_user, request_id=request_id)
                        yield _sse_event({"event": "error", "message": str(message), "status": 400})
                        return
                    if event_name == "done":
                        if event.get("usage"):
                            usage = event.get("usage") or usage
                        if event.get("requestId"):
                            request_id = event.get("requestId")
            content = "".join(content_parts)
            done_payload = {"event": "done", "content": content, "usage": usage or {}}
            if _is_structured_response(structured_response):
                parsed = _parse_content(content)
                done_payload.update(parsed)
            cost_micro_usd = _calculate_cost_micro_usd(model, usage)
            governance.finish(invocation, status_value="success", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=cost_micro_usd)
            invocation_closed = True
            self._log_call(provider, model, profile, "success", start, usage, user=current_user, cost_micro_usd=cost_micro_usd, request_id=request_id)
            done_sent = True
            yield _sse_event(done_payload)
        except AiGovernanceBlocked as exc:
            governance.block_invocation(invocation)
            invocation_closed = True
            self._log_call(provider, model, profile, "blocked", start, usage, str(exc), user=current_user, request_id=request_id)
            yield _sse_event({"event": "error", "message": str(exc), "status": 429})
        except UnsupportedCapabilityError as exc:
            governance.finish(invocation, status_value="unsupported", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
            invocation_closed = True
            self._log_call(provider, model, profile, "unsupported", start, usage, str(exc), user=current_user, request_id=request_id)
            yield _sse_event({"event": "error", "message": str(exc), "status": 501})
        except Exception as exc:
            if not emitted_delta:
                fallback = self._stream_fallback(
                    profile,
                    messages,
                    request_options,
                    structured_response,
                    response_format_overridden,
                    current_user=current_user,
                )
                if fallback is not None:
                    governance.finish(invocation, status_value="error", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
                    invocation_closed = True
                    self._log_call(provider, model, profile, "error", start, usage, str(exc), user=current_user, request_id=request_id)
                    yield from fallback
                    return
            if not done_sent:
                governance.finish(invocation, status_value="error", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)
                invocation_closed = True
                self._log_call(provider, model, profile, "error", start, usage, str(exc), user=current_user, request_id=request_id)
                yield _sse_event({"event": "error", "message": f"模型调用失败: {exc}", "status": 400})
        finally:
            if invocation is not None and not invocation_closed:
                governance.finish(invocation, status_value="error", user=current_user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=0)

    def _stream_fallback(
        self,
        profile: AiModelProfile,
        messages: list[dict[str, Any]],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
    ) -> Iterable[str] | None:
        if not profile.fallback_profile_id:
            return None
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
        return self._stream_invoke(
            {"provider": provider, "model": model, "profile": fallback, "options": options},
            current_user=current_user,
            messages=messages,
            options=options,
            request_options=request_options,
            structured_response=structured_response or options.get("response_format"),
            response_format_overridden=response_format_overridden,
        )

    def _fallback(
        self,
        profile: AiModelProfile,
        method: str,
        kwargs: dict[str, Any],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
    ) -> dict | None:
        if not profile.fallback_profile_id:
            return None
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
            request_options=request_options,
            structured_response=structured_response or options.get("response_format"),
            response_format_overridden=response_format_overridden,
            **fallback_kwargs,
        )

    def _log_call(
        self,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
        status_value: str,
        start: float,
        usage: dict,
        error: str | None = None,
        user: User | None = None,
        cost_micro_usd: int = 0,
        request_id: str | None = None,
    ) -> None:
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
        )
        self.session.add(log)
        self.session.commit()
