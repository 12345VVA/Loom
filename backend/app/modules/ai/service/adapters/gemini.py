from __future__ import annotations

from typing import Any

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, normalize_usage


class GeminiAdapter(BaseHttpAdapter):
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        payload = {
            "contents": [_gemini_content(item) for item in messages if item.get("role") != "system"],
            **options,
        }
        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        data, response = self._post(f"/models/{model}:generateContent?key={self.api_key or ''}", payload, self._headers())
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        return {
            "content": "\n".join(part.get("text", "") for part in parts if part.get("text")),
            "raw": data,
            "usage": normalize_usage(data.get("usageMetadata")),
            "requestId": response.headers.get("x-request-id"),
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        raise UnsupportedCapabilityError("Gemini 流式接口将在 SSE 层统一接入")

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        texts = input if isinstance(input, list) else [input]
        data_items = []
        for text in texts:
            data, _ = self._post(
                f"/models/{model}:embedContent?key={self.api_key or ''}",
                {"content": {"parts": [{"text": text}]}, **options},
                self._headers(),
            )
            data_items.append({"embedding": (data.get("embedding") or {}).get("values", [])})
        return {"data": data_items, "raw": {"data": data_items}, "usage": {}}

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Gemini 图像/视频生成需按具体模型 API 继续扩展")

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Gemini 视频生成需按具体模型 API 继续扩展")

    def test(self) -> dict:
        data, _ = self._get(f"/models?key={self.api_key or ''}", self._headers())
        return {"success": True, "count": len(data.get("models", []))}


def _gemini_content(message: dict[str, Any]) -> dict:
    role = "model" if message.get("role") == "assistant" else "user"
    return {"role": role, "parts": [{"text": str(message.get("content") or "")}]}
