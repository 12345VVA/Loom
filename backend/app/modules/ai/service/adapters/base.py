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


class AdapterInputError(RuntimeError):
    """适配器参数/配置类错误（wan2.6 不支持 negative_prompt、Seedream 尺寸不足、
    多模态 data URI 非法等）。

    与 UpstreamApiError（上游故障，可重试可降级）二分类（评审 AI-009）：这类错误
    换一个模型重跑结果相同，降级只会二次计费并产生误导性 error 审计。运行时对它
    不重试、不 fallback，直接以 4xx 语义透出。
    """


class UpstreamApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class BaseHttpAdapter:
    default_base_url = ""
    supported_capabilities: set[str] = set()

    def __init__(self, provider: AiProvider):
        self.provider = provider
        # AI-017 实例池：适配器跨请求复用，provider 是某次请求 Session 的 ORM 实体
        # （Session 默认 expire_on_commit=True，commit 后过期、close 后 detached——
        # 方法内再访问 self.provider.xxx 会抛 DetachedInstanceError），初始化期必须
        # 物化全部所需值，禁止方法内惰性访问
        self.adapter_code = provider.adapter
        self.provider_code = provider.code
        self.api_key = decrypt_secret(provider.api_key_cipher)
        self.base_url = (provider.base_url or self.default_base_url).rstrip("/")
        self.extra_config = self._loads(provider.extra_config)
        self.timeout = float(self.extra_config.get("timeout", 60))

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 chat")

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 stream_chat")

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 embedding")

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 image")

    def audio(self, *, model: str, input: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 audio")

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 video")

    def rerank(self, *, model: str, query: str, documents: list[str], options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持 rerank")

    def test(self) -> dict:
        raise UnsupportedCapabilityError(f"{self.adapter_code} 暂不支持连接测试")

    def list_models(self) -> list[dict[str, Any]]:
        data, _ = self._get(getattr(self, "models_path", "/models"))
        items = data.get("data") or data.get("models") or []
        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            code = item.get("id") or item.get("name") or item.get("model")
            if code:
                result.append({"code": str(code), "name": str(item.get("display_name") or item.get("name") or code)})
        return result

    def capability_status(self) -> dict:
        return {
            "adapter": self.adapter_code,
            "supportedCapabilities": sorted(self.supported_capabilities),
        }

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def _post(
        self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None, base_url: str | None = None
    ) -> tuple[dict, httpx.Response]:
        response = httpx.post(
            f"{(base_url or self.base_url).rstrip('/')}{path}",
            json=payload,
            headers=headers or self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(response)
        return response.json(), response

    def _get(
        self, path: str, headers: dict[str, str] | None = None, base_url: str | None = None
    ) -> tuple[dict, httpx.Response]:
        response = httpx.get(
            f"{(base_url or self.base_url).rstrip('/')}{path}",
            headers=headers or self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(response)
        return response.json(), response

    def _raise_for_status(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            request_id = response.headers.get("x-request-id") or response.headers.get("x-tt-logid")
            message = _extract_error_message(response)
            detail = f"{response.status_code} {response.reason_phrase}"
            if message:
                detail = f"{detail}: {message}"
            if request_id:
                detail = f"{detail} (requestId: {request_id})"
            raise UpstreamApiError(detail, status_code=response.status_code, request_id=request_id) from exc

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


_STREAM_OPTION_REJECTED_STATUS = frozenset({400, 422})
_STREAM_OPTION_MARKERS = ("stream_options", "include_usage")


def stream_options_unsupported(exc: BaseException) -> bool:
    """判断异常是否由「上游不认 stream_options」引起（AI-003 兜底）。

    流式计量依赖 OpenAI 协议的 stream_options.include_usage，但该字段并非所有兼容
    网关都实现：旧版 Ollama、部分国产网关按参数白名单校验，见到即返回 400/422
    （如 "extra fields not permitted"）。这类失败发生在首个 delta 之前，去掉该字段
    重试一次即可降级为「有内容、无 usage」，优于整条流失败。

    仅在状态码属参数类 4xx 且报文点名该字段时判定为真，避免把无关 400（如模型
    不存在、messages 非法）误判成可降级，从而掩盖真实错误。
    """
    if getattr(exc, "status_code", None) not in _STREAM_OPTION_REJECTED_STATUS:
        return False
    message = str(exc).lower()
    return any(marker in message for marker in _STREAM_OPTION_MARKERS)


def normalize_usage(data: dict[str, Any] | None) -> dict[str, int]:
    if not data:
        return {}
    return {
        "promptTokens": int(
            data.get("prompt_tokens")
            or data.get("promptTokens")
            or data.get("promptTokenCount")
            or data.get("input_tokens")
            or data.get("inputTokens")
            or 0
        ),
        "completionTokens": int(
            data.get("completion_tokens")
            or data.get("completionTokens")
            or data.get("candidatesTokenCount")
            or data.get("output_tokens")
            or data.get("outputTokens")
            or 0
        ),
        "totalTokens": int(
            data.get("total_tokens") or data.get("totalTokens") or data.get("totalTokenCount") or data.get("total") or 0
        ),
    }


def openai_chat_result(data: dict[str, Any], response: httpx.Response | None = None) -> dict:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    result = {
        "content": message.get("content") or choice.get("text"),
        "raw": data,
        "usage": normalize_usage(data.get("usage")),
        "requestId": response.headers.get("x-request-id") if response else None,
    }
    # DeepSeek 等思考模型把思维链放在 reasoning_content（正文仍是 content），单独透出
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if reasoning:
        result["reasoning"] = reasoning
    return result


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


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text[:1000]
    if not isinstance(data, dict):
        return str(data)[:1000]
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("msg") or error.get("code")
        if message:
            return str(message)[:1000]
    return str(data.get("message") or data.get("msg") or data.get("error") or data)[:1000]
