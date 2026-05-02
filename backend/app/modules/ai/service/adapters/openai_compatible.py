from __future__ import annotations

from typing import Any

from openai import OpenAI

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, normalize_usage


class OpenAICompatibleAdapter(BaseHttpAdapter):
    def __init__(self, provider: AiProvider):
        super().__init__(provider)
        self.client = OpenAI(api_key=self.api_key or "EMPTY", base_url=self.base_url or None)

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        response = self.client.chat.completions.create(model=model, messages=messages, **options)
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None) if choice else None
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        return {"content": getattr(message, "content", None), "raw": data, "usage": normalize_usage(data.get("usage") if isinstance(data, dict) else {})}

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        stream = self.client.chat.completions.create(model=model, messages=messages, stream=True, **options)
        for chunk in stream:
            data = chunk.model_dump(mode="json") if hasattr(chunk, "model_dump") else {}
            delta = (((data.get("choices") or [{}])[0]).get("delta") or {}).get("content")
            yield {"event": "delta", "content": delta, "raw": data}

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        response = self.client.embeddings.create(model=model, input=input, **options)
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        return {"data": data.get("data", []), "raw": data, "usage": normalize_usage(data.get("usage"))}

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        response = self.client.images.generate(model=model, prompt=prompt, **options)
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        return {"data": data.get("data", []), "raw": data, "usage": {}}

    def audio(self, *, model: str, input: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("OpenAI Compatible 音频接口暂未统一")

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("OpenAI Compatible 视频接口暂未统一")

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("OpenAI Compatible 重排接口暂未统一")

    def test(self) -> dict:
        models = self.client.models.list()
        data = models.model_dump(mode="json").get("data", []) if hasattr(models, "model_dump") else []
        return {"success": True, "count": len(data)}
