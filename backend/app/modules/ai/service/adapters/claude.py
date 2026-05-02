from __future__ import annotations

from typing import Any

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, normalize_usage


class ClaudeAdapter(BaseHttpAdapter):
    default_base_url = "https://api.anthropic.com/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.extra_config.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json",
        }

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        payload = {
            "model": model,
            "messages": [{"role": _claude_role(item), "content": item.get("content", "")} for item in messages if item.get("role") != "system"],
            "max_tokens": options.pop("max_tokens", options.pop("maxTokens", 1024)),
            **options,
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
        raise UnsupportedCapabilityError("Claude 流式接口将在 SSE 层统一接入")

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
