from __future__ import annotations

import logging
from typing import Any

import httpx

from app.modules.ai.service.adapters.base import (
    BaseHttpAdapter,
    iter_sse_events,
    loads_json,
    normalize_usage,
    openai_chat_result,
    openai_embedding_result,
    openai_image_result,
    stream_options_unsupported,
)

logger = logging.getLogger(__name__)


class OpenAIHttpAdapter(BaseHttpAdapter):
    supported_capabilities = {"chat", "stream_chat", "embedding", "image", "rerank"}
    chat_path = "/chat/completions"
    embeddings_path = "/embeddings"
    images_path = "/images/generations"
    models_path = "/models"

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        data, response = self._post(self.chat_path, {"model": model, "messages": messages, **options})
        return openai_chat_result(data, response)

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        options = dict(options or {})
        # OpenAI 兼容协议下 usage 仅在带 stream_options.include_usage 的最后一帧返回，
        # 不传则流式请求零计量，token/成本治理对流式流量完全失效（AI-003）
        stream_options = {"include_usage": True}
        user_stream_options = options.pop("stream_options", None)
        if isinstance(user_stream_options, dict):
            stream_options.update(user_stream_options)
        payload = {
            "model": model,
            "messages": messages,
            **options,
            "stream": True,
            "stream_options": stream_options,
        }
        yielded = False
        try:
            for event in self._iter_stream_events(payload):
                yielded = True
                yield event
        except Exception as exc:
            # 白名单网关见到 stream_options 直接 400/422。此时尚未产出任何 delta，
            # 去字段重试不会重复正文，代价仅是该条流失去 usage 计量
            if yielded or not stream_options_unsupported(exc):
                raise
            logger.warning(
                "上游拒绝 stream_options，已去字段重试（本条流不计 token）",
                extra={
                    "provider_adapter": self.adapter_code,
                    "provider_code": self.provider_code,
                    "base_url": self.base_url,
                    "model": model,
                    "user_supplied": isinstance(user_stream_options, dict),
                    "error_message": str(exc)[:500],
                },
            )
            payload.pop("stream_options", None)
            yield from self._iter_stream_events(payload)

    def _iter_stream_events(self, payload: dict[str, Any]):
        with httpx.stream(
            "POST",
            f"{self.base_url}{self.chat_path}",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        ) as response:
            if getattr(response, "is_error", False):
                if hasattr(response, "read"):
                    response.read()
            self._raise_for_status(response)
            request_id = response.headers.get("x-request-id")
            for event in iter_sse_events(response.iter_lines()):
                value = event.get("data")
                if value == "[DONE]":
                    yield {"event": "done", "requestId": request_id}
                    continue
                data = loads_json(value)
                choice = (data.get("choices") or [{}])[0]
                message_delta = choice.get("delta") or {}
                delta = message_delta.get("content")
                reasoning_delta = message_delta.get("reasoning_content") or message_delta.get("reasoning")
                finish_reason = choice.get("finish_reason")
                usage = normalize_usage(data.get("usage")) if data.get("usage") else {}
                # DeepSeek 等思考模型的思维链增量，按 thinking_delta 事件透传（不混入正文）
                if reasoning_delta:
                    yield {"event": "thinking_delta", "content": reasoning_delta, "raw": data, "requestId": request_id}
                if delta:
                    yield {"event": "delta", "content": delta, "raw": data, "requestId": request_id}
                if usage or finish_reason:
                    yield {
                        "event": "done",
                        "raw": data,
                        "usage": usage,
                        "finishReason": finish_reason,
                        "requestId": request_id,
                    }

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        data, response = self._post(self.embeddings_path, {"model": model, "input": input, **options})
        return openai_embedding_result(data, response)

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        data, response = self._post(self.images_path, {"model": model, "prompt": prompt, **options})
        return openai_image_result(data, response)

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        path = self.extra_config.get("rerank_path", "/rerank")
        data, response = self._post(path, {"model": model, "query": query, "documents": documents, **options})
        return {
            "data": data.get("results") or data.get("data") or [],
            "raw": data,
            "usage": {},
            "requestId": response.headers.get("x-request-id"),
        }

    def test(self) -> dict:
        try:
            data, _ = self._get(self.models_path)
            return {"success": True, "count": len(data.get("data", data.get("models", [])))}
        except Exception:
            if not self.extra_config.get("skip_model_list_check"):
                raise
            return {"success": True, "message": "厂商未提供模型列表接口，已跳过列表检查"}
