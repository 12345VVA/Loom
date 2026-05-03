from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, iter_sse_events, loads_json, normalize_usage


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
        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", call_options.pop("maxTokens", 1024))
        payload = {
            "model": model,
            "messages": [{"role": _claude_role(item), "content": item.get("content", "")} for item in messages if item.get("role") != "system"],
            "max_tokens": max_tokens,
            **call_options,
        }
        if system_text:
            payload["system"] = system_text
        data, response = self._post("/messages", payload, self._headers())
        return {
            "content": "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"),
            "raw": data,
            "usage": normalize_usage(data.get("usage")),
            "requestId": response.headers.get("request-id"),
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", call_options.pop("maxTokens", 1024))
        payload = {
            "model": model,
            "messages": [{"role": _claude_role(item), "content": item.get("content", "")} for item in messages if item.get("role") != "system"],
            "max_tokens": max_tokens,
            "stream": True,
            **call_options,
        }
        if system_text:
            payload["system"] = system_text
        with httpx.stream("POST", f"{self.base_url}/messages", json=payload, headers=self._headers(), timeout=self.timeout) as response:
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
                        yield {"event": "thinking_delta", "content": delta.get("thinking"), "raw": data, "requestId": request_id}
                    elif delta_type == "input_json_delta" and delta.get("partial_json"):
                        yield {"event": "tool_delta", "content": delta.get("partial_json"), "raw": data, "requestId": request_id}
                elif event_type == "message_delta":
                    usage = normalize_usage((data.get("usage") or {}))
                    if usage:
                        yield {"event": "done", "raw": data, "usage": usage, "requestId": request_id}
                elif event_type == "message_stop":
                    yield {"event": "done", "raw": data, "requestId": request_id}
                elif event_type == "error":
                    error = data.get("error") or {}
                    yield {"event": "error", "content": error.get("message") or "Claude 流式调用失败", "raw": data, "requestId": request_id}

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
