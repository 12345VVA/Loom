from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.service.adapters.base import (
    BaseHttpAdapter,
    UnsupportedCapabilityError,
    aiter_sse_events,
    iter_sse_events,
    loads_json,
    normalize_usage,
)
from app.modules.ai.service.adapters.media_fetch import extract_system_text, fetch_image_as_data_uri, parse_data_uri


def _to_claude_content(content: Any) -> Any:
    """OpenAI 风格 IR parts → Claude 原生 content（WFI-2b）。

    - str：原样透传；
    - list：text part → ``{"type": "text"}``；image_url part → 取回图片转
      ``{"type": "image", "source": {"type": "base64", ...}}``（Claude Messages API
      无 image_url 形态，必须 base64 内联）。取回失败抛 UpstreamApiError（显式失败，
      不静默丢图）。
    """
    if not isinstance(content, list):
        return content
    parts: list[dict[str, Any]] = []
    for p in content:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            parts.append({"type": "text", "text": str(p.get("text", ""))})
        elif p.get("type") == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            data_uri = fetch_image_as_data_uri(url)
            mime_type, b64_data = parse_data_uri(data_uri)
            parts.append({"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64_data}})
    return parts or ""


class ClaudeAdapter(BaseHttpAdapter):
    default_base_url = "https://api.anthropic.com/v1"
    supported_capabilities = {"chat", "stream_chat", "thinking"}

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.extra_config.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json",
        }

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        system_text = extract_system_text(messages)
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", call_options.pop("maxTokens", 1024))
        # Claude API 不支持 OpenAI 风格的 response_format，需要移除以避免参数错误
        call_options.pop("response_format", None)
        payload = {
            "model": model,
            "messages": [
                {"role": _claude_role(item), "content": _to_claude_content(item.get("content", ""))}
                for item in messages
                if item.get("role") != "system"
            ],
            "max_tokens": max_tokens,
            **call_options,
        }
        if system_text:
            payload["system"] = system_text
        data, response = self._post("/messages", payload, self._headers())
        return {
            "content": "\n".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ),
            "raw": data,
            "usage": normalize_usage(data.get("usage")),
            "requestId": response.headers.get("request-id"),
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        system_text = extract_system_text(messages)
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", call_options.pop("maxTokens", 1024))
        # Claude API 不支持 OpenAI 风格的 response_format，需要移除以避免参数错误
        call_options.pop("response_format", None)
        payload = {
            "model": model,
            "messages": [
                {"role": _claude_role(item), "content": _to_claude_content(item.get("content", ""))}
                for item in messages
                if item.get("role") != "system"
            ],
            "max_tokens": max_tokens,
            "stream": True,
            **call_options,
        }
        if system_text:
            payload["system"] = system_text
        with httpx.stream(
            "POST", f"{self.base_url}/messages", json=payload, headers=self._headers(), timeout=self.timeout
        ) as response:
            response.raise_for_status()
            request_id = response.headers.get("request-id")
            for event in iter_sse_events(response.iter_lines()):
                data = loads_json(event.get("data"))
                event_type = event.get("event") or data.get("type")
                if event_type == "content_block_delta":
                    delta = data.get("delta") or {}
                    delta_type = delta.get("type")
                    if delta_type == "text_delta" and delta.get("text"):
                        yield {"event": "delta", "content": delta.get("text"), "raw": data, "requestId": request_id}
                    elif delta_type == "thinking_delta" and delta.get("thinking"):
                        yield {
                            "event": "thinking_delta",
                            "content": delta.get("thinking"),
                            "raw": data,
                            "requestId": request_id,
                        }
                    elif delta_type == "input_json_delta" and delta.get("partial_json"):
                        yield {
                            "event": "tool_delta",
                            "content": delta.get("partial_json"),
                            "raw": data,
                            "requestId": request_id,
                        }
                elif event_type == "message_delta":
                    usage = normalize_usage(data.get("usage") or {})
                    if usage:
                        yield {"event": "done", "raw": data, "usage": usage, "requestId": request_id}
                elif event_type == "message_stop":
                    yield {"event": "done", "raw": data, "requestId": request_id}
                elif event_type == "error":
                    error = data.get("error") or {}
                    yield {
                        "event": "error",
                        "content": error.get("message") or "Claude 流式调用失败",
                        "raw": data,
                        "requestId": request_id,
                    }

    async def stream_chat_async(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        """stream_chat 的异步通道（异步审查 P0-4）：payload 构造与事件解析逐条对齐，
        改任一侧必须同步另一侧。"""
        system_text = extract_system_text(messages)
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", call_options.pop("maxTokens", 1024))
        call_options.pop("response_format", None)
        payload = {
            "model": model,
            "messages": [
                {"role": _claude_role(item), "content": _to_claude_content(item.get("content", ""))}
                for item in messages
                if item.get("role") != "system"
            ],
            "max_tokens": max_tokens,
            "stream": True,
            **call_options,
        }
        if system_text:
            payload["system"] = system_text
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/messages", json=payload, headers=self._headers()
            ) as response:
                response.raise_for_status()
                request_id = response.headers.get("request-id")
                async for event in aiter_sse_events(response.aiter_lines()):
                    data = loads_json(event.get("data"))
                    event_type = event.get("event") or data.get("type")
                    if event_type == "content_block_delta":
                        delta = data.get("delta") or {}
                        delta_type = delta.get("type")
                        if delta_type == "text_delta" and delta.get("text"):
                            yield {"event": "delta", "content": delta.get("text"), "raw": data, "requestId": request_id}
                        elif delta_type == "thinking_delta" and delta.get("thinking"):
                            yield {
                                "event": "thinking_delta",
                                "content": delta.get("thinking"),
                                "raw": data,
                                "requestId": request_id,
                            }
                        elif delta_type == "input_json_delta" and delta.get("partial_json"):
                            yield {
                                "event": "tool_delta",
                                "content": delta.get("partial_json"),
                                "raw": data,
                                "requestId": request_id,
                            }
                    elif event_type == "message_delta":
                        usage = normalize_usage(data.get("usage") or {})
                        if usage:
                            yield {"event": "done", "raw": data, "usage": usage, "requestId": request_id}
                    elif event_type == "message_stop":
                        yield {"event": "done", "raw": data, "requestId": request_id}
                    elif event_type == "error":
                        error = data.get("error") or {}
                        yield {
                            "event": "error",
                            "content": error.get("message") or "Claude 流式调用失败",
                            "raw": data,
                            "requestId": request_id,
                        }

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Claude 原生 API 暂不提供通用 embedding")

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Claude 原生 API 暂不提供图像生成")

    def audio(self, *, model: str, input: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Claude 原生 API 暂不提供音频生成")

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Claude 原生 API 暂不提供视频生成")

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Claude 原生 API 暂不提供 rerank")

    def test(self) -> dict:
        return {"success": True, "message": "Claude API 未提供通用模型列表，已完成本地配置检查"}


def _claude_role(message: dict[str, Any]) -> str:
    return "assistant" if message.get("role") == "assistant" else "user"
