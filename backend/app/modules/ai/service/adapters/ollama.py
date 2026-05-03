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
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": True, "options": options},
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = _loads_line(line)
                content = (data.get("message") or {}).get("content")
                if content:
                    yield {"event": "delta", "content": content, "raw": data}
                if data.get("done"):
                    usage = {
                        "promptTokens": data.get("prompt_eval_count") or 0,
                        "completionTokens": data.get("eval_count") or 0,
                        "totalTokens": (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0),
                    }
                    yield {"event": "done", "raw": data, "usage": usage}

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


def _loads_line(line: str | bytes) -> dict[str, Any]:
    import json

    value = line.decode("utf-8") if isinstance(line, bytes) else line
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
