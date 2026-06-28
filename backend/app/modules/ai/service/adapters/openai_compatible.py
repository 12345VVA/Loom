from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, normalize_usage
from app.modules.ai.service.utils import (
    extract_request_id,
    sanitize_options_for_log,
    summarize_image_result_items,
    summarize_prompt,
)

logger = logging.getLogger(__name__)
_OPENAI_IMAGE_ALLOWED_OPTION_KEYS = {"size", "n", "response_format", "quality", "style", "user"}


class OpenAICompatibleAdapter(BaseHttpAdapter):
    supported_capabilities = {"chat", "stream_chat", "embedding", "image"}

    def __init__(self, provider: AiProvider):
        super().__init__(provider)
        self.client = OpenAI(api_key=self.api_key or "EMPTY", base_url=self.base_url or None)

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        response = self.client.chat.completions.create(model=model, messages=messages, **options)
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None) if choice else None
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        return {
            "content": getattr(message, "content", None),
            "raw": data,
            "usage": normalize_usage(data.get("usage") if isinstance(data, dict) else {}),
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        stream = self.client.chat.completions.create(model=model, messages=messages, stream=True, **options)
        for chunk in stream:
            data = chunk.model_dump(mode="json") if hasattr(chunk, "model_dump") else {}
            choice = (data.get("choices") or [{}])[0]
            delta = (choice.get("delta") or {}).get("content")
            finish_reason = choice.get("finish_reason")
            usage = normalize_usage(data.get("usage")) if data.get("usage") else {}
            if delta:
                yield {"event": "delta", "content": delta, "raw": data}
            if usage or finish_reason:
                yield {"event": "done", "raw": data, "usage": usage, "finishReason": finish_reason}

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        response = self.client.embeddings.create(model=model, input=input, **options)
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        return {"data": data.get("data", []), "raw": data, "usage": normalize_usage(data.get("usage"))}

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        normalized_options = dict(options or {})

        # 针对 gpt-image-2 模型的特定约束做自动转换/裁剪
        is_gpt_image_2 = model.lower().startswith("gpt-image-2")
        if is_gpt_image_2:
            if normalized_options.get("n", 1) > 1:
                logger.warning(
                    f"Model {model} only supports n=1. Automatically truncating n to 1.",
                    extra={"model": model, "original_n": normalized_options["n"]},
                )
                normalized_options["n"] = 1
            if normalized_options.get("response_format") != "b64_json":
                normalized_options["response_format"] = "b64_json"

        allowed_options = {
            key: value for key, value in normalized_options.items() if key in _OPENAI_IMAGE_ALLOWED_OPTION_KEYS
        }
        dropped_options = {
            key: value for key, value in normalized_options.items() if key not in _OPENAI_IMAGE_ALLOWED_OPTION_KEYS
        }

        extra_body = {}
        if is_gpt_image_2:
            for key in list(dropped_options.keys()):
                if key not in {"async", "force_async", "prompt_extend"}:
                    extra_body[key] = dropped_options.pop(key)

        if extra_body:
            allowed_options["extra_body"] = extra_body

        logger.info(
            "OpenAI Compatible 生图上游请求开始",
            extra={
                "provider_adapter": self.provider.adapter,
                "provider_code": self.provider.code,
                "base_url": self.base_url,
                "model": model,
                "prompt": summarize_prompt(prompt),
                "options": sanitize_options_for_log(normalized_options),
                "filtered_options": sanitize_options_for_log(allowed_options),
            },
        )
        if dropped_options:
            logger.warning(
                "OpenAI Compatible 生图参数已拦截非标准字段",
                extra={
                    "provider_adapter": self.provider.adapter,
                    "provider_code": self.provider.code,
                    "base_url": self.base_url,
                    "model": model,
                    "dropped_option_keys": sorted(dropped_options.keys()),
                    "dropped_options": sanitize_options_for_log(dropped_options),
                },
            )
        try:
            response = self.client.images.generate(model=model, prompt=prompt, **allowed_options)
        except Exception as exc:
            # 仅记录 adapter 层业务上下文（不含 traceback）；
            # 完整堆栈由 runtime_service 统一打印，避免同一异常被重复输出。
            logger.error(
                "OpenAI Compatible 生图上游请求失败",
                extra={
                    "provider_adapter": self.provider.adapter,
                    "provider_code": self.provider.code,
                    "base_url": self.base_url,
                    "model": model,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "filtered_options": sanitize_options_for_log(allowed_options),
                },
            )
            raise
        data = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        request_id = extract_request_id(response)
        usage = normalize_usage(data.get("usage")) if isinstance(data, dict) else {}
        logger.info(
            "OpenAI Compatible 生图上游请求完成",
            extra={
                "provider_adapter": self.provider.adapter,
                "provider_code": self.provider.code,
                "base_url": self.base_url,
                "model": model,
                "upstream_request_id": request_id,
                "usage": usage,
                "image_count": len(data.get("data", [])),
                "images": summarize_image_result_items(data.get("data", [])),
            },
        )
        return {"data": data.get("data", []), "raw": data, "usage": usage, "requestId": request_id}

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

    def list_models(self) -> list[dict[str, Any]]:
        models = self.client.models.list()
        data = models.model_dump(mode="json").get("data", []) if hasattr(models, "model_dump") else []
        result: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            code = item.get("id") or item.get("name")
            if code:
                result.append({"code": str(code), "name": str(item.get("name") or code)})
        return result
