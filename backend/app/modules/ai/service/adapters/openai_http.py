from __future__ import annotations

from typing import Any

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, openai_chat_result, openai_embedding_result, openai_image_result


class OpenAIHttpAdapter(BaseHttpAdapter):
    chat_path = "/chat/completions"
    embeddings_path = "/embeddings"
    images_path = "/images/generations"
    models_path = "/models"

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        data, response = self._post(self.chat_path, {"model": model, "messages": messages, **options})
        return openai_chat_result(data, response)

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 流式接口将在 SSE 层统一接入")

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        data, response = self._post(self.embeddings_path, {"model": model, "input": input, **options})
        return openai_embedding_result(data, response)

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        data, response = self._post(self.images_path, {"model": model, "prompt": prompt, **options})
        return openai_image_result(data, response)

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        path = self.extra_config.get("rerank_path", "/rerank")
        data, response = self._post(path, {"model": model, "query": query, "documents": documents, **options})
        return {"data": data.get("results") or data.get("data") or [], "raw": data, "usage": {}, "requestId": response.headers.get("x-request-id")}

    def test(self) -> dict:
        try:
            data, _ = self._get(self.models_path)
            return {"success": True, "count": len(data.get("data", data.get("models", [])))}
        except Exception:
            if not self.extra_config.get("skip_model_list_check"):
                raise
            return {"success": True, "message": "厂商未提供模型列表接口，已跳过列表检查"}
