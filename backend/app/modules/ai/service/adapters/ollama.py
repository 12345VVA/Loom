from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError


class OllamaAdapter(BaseHttpAdapter):
    default_base_url = "http://localhost:11434"

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        response = httpx.post(f"{self.base_url}/api/chat", json={"model": model, "messages": messages, "stream": False, "options": options}, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return {
            "content": (data.get("message") or {}).get("content"),
            "raw": data,
            "usage": {
                "promptTokens": data.get("prompt_eval_count") or 0,
                "completionTokens": data.get("eval_count") or 0,
                "totalTokens": (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0),
            },
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        raise UnsupportedCapabilityError("Ollama 流式接口将在 SSE 层统一接入")

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        text = input if isinstance(input, str) else "\n".join(input)
        response = httpx.post(f"{self.base_url}/api/embeddings", json={"model": model, "prompt": text, **options}, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return {"data": [{"embedding": data.get("embedding", [])}], "raw": data, "usage": {}}

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Ollama 暂不支持统一图像生成接口")

    def test(self) -> dict:
        response = httpx.get(f"{self.base_url}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "count": len(data.get("models", []))}
