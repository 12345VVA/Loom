"""
AI 厂商适配器基础工具。
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import httpx

from app.core.secret import decrypt_secret
from app.modules.ai.model.ai import AiProvider


class UnsupportedCapabilityError(NotImplementedError):
    pass


class BaseHttpAdapter:
    default_base_url = ""

    def __init__(self, provider: AiProvider):
        self.provider = provider
        self.api_key = decrypt_secret(provider.api_key_cipher)
        self.base_url = (provider.base_url or self.default_base_url).rstrip("/")
        self.extra_config = self._loads(provider.extra_config)
        self.timeout = float(self.extra_config.get("timeout", 60))

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 chat")

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 stream_chat")

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 embedding")

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 image")

    def audio(self, *, model: str, input: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 audio")

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 video")

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持 rerank")

    def test(self) -> dict:
        raise UnsupportedCapabilityError(f"{self.provider.adapter} 暂不支持连接测试")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[dict, httpx.Response]:
        response = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=headers or self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json(), response

    def _get(self, path: str, headers: dict[str, str] | None = None) -> tuple[dict, httpx.Response]:
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=headers or self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json(), response

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def normalize_usage(data: dict[str, Any] | None) -> dict[str, int]:
    if not data:
        return {}
    return {
        "promptTokens": int(data.get("prompt_tokens") or data.get("promptTokens") or data.get("promptTokenCount") or data.get("input_tokens") or data.get("inputTokens") or 0),
        "completionTokens": int(data.get("completion_tokens") or data.get("completionTokens") or data.get("candidatesTokenCount") or data.get("output_tokens") or data.get("outputTokens") or 0),
        "totalTokens": int(data.get("total_tokens") or data.get("totalTokens") or data.get("totalTokenCount") or data.get("total") or 0),
    }


def openai_chat_result(data: dict[str, Any], response: httpx.Response | None = None) -> dict:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "content": message.get("content") or choice.get("text"),
        "raw": data,
        "usage": normalize_usage(data.get("usage")),
        "requestId": response.headers.get("x-request-id") if response else None,
    }


def openai_embedding_result(data: dict[str, Any], response: httpx.Response | None = None) -> dict:
    return {
        "data": data.get("data", []),
        "raw": data,
        "usage": normalize_usage(data.get("usage")),
        "requestId": response.headers.get("x-request-id") if response else None,
    }


def openai_image_result(data: dict[str, Any], response: httpx.Response | None = None) -> dict:
    return {
        "data": data.get("data", []),
        "raw": data,
        "usage": normalize_usage(data.get("usage")),
        "requestId": response.headers.get("x-request-id") if response else None,
    }


def iter_sse_events(lines: Iterable[str | bytes]) -> Iterable[dict[str, str | None]]:
    event_name: str | None = None
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        line = line.rstrip("\r")
        if not line:
            if data_lines:
                yield {"event": event_name, "data": "\n".join(data_lines)}
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield {"event": event_name, "data": "\n".join(data_lines)}


def loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
