from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.service.adapters.base import BaseHttpAdapter, iter_sse_events, loads_json, normalize_usage, openai_chat_result, openai_embedding_result, openai_image_result


class OpenAIHttpAdapter(BaseHttpAdapter):
    chat_path = "/chat/completions"
    embeddings_path = "/embeddings"
    images_path = "/images/generations"
    models_path = "/models"

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        data, response = self._post(self.chat_path, {"model": model, "messages": messages, **options})
        return openai_chat_result(data, response)

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        payload = {"model": model, "messages": messages, **options, "stream": True}
        with httpx.stream(
            "POST",
            f"{self.base_url}{self.chat_path}",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            request_id = response.headers.get("x-request-id")
            for event in iter_sse_events(response.iter_lines()):
                value = event.get("data")
                if value == "[DONE]":
                    yield {"event": "done", "requestId": request_id}
                    continue
                data = loads_json(value)
                choice = (data.get("choices") or [{}])[0]
                delta = (choice.get("delta") or {}).get("content")
                finish_reason = choice.get("finish_reason")
                usage = normalize_usage(data.get("usage")) if data.get("usage") else {}
                if delta:
                    yield {"event": "delta", "content": delta, "raw": data, "requestId": request_id}
                if usage or finish_reason:
                    yield {"event": "done", "raw": data, "usage": usage, "finishReason": finish_reason, "requestId": request_id}

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
