from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.base import UpstreamApiError, normalize_usage, openai_image_result
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter


class BailianAdapter(OpenAIHttpAdapter):
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        options = dict(options or {})
        protocol = _resolve_bailian_image_protocol(model, options)
        if protocol == "wan2.6-sync":
            return self._image_wan26_sync(model=model, prompt=prompt, options=options)
        if protocol == "wan2.6-async":
            return self._image_async(
                path="/services/aigc/image-generation/generation",
                payload=_build_bailian_wan26_async_payload(model, prompt, options),
            )
        return self._image_async(
            path="/services/aigc/text2image/image-synthesis",
            payload=_build_bailian_legacy_image_payload(model, prompt, options),
        )

    def _image_wan26_sync(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        data, response = self._post_dashscope(
            "/services/aigc/multimodal-generation/generation",
            _build_bailian_wan26_sync_payload(model, prompt, options),
        )
        return _bailian_image_result(
            data, response.headers.get("x-request-id") or response.headers.get("x-dashscope-request-id")
        )

    def _image_async(self, *, path: str, payload: dict[str, Any]) -> dict:
        data, response = self._post_dashscope(path, payload, extra_headers={"X-DashScope-Async": "enable"})
        task_id = _extract_bailian_task_id(data)
        if not task_id:
            raise UpstreamApiError(
                "百炼生图任务创建失败: 响应缺少 task_id", request_id=_bailian_request_id(response.headers)
            )
        final_data, final_response = self._poll_bailian_task(task_id)
        request_id = _bailian_request_id(final_response.headers) or _bailian_request_id(response.headers) or task_id
        result = _bailian_image_result(final_data, request_id)
        result["taskId"] = task_id
        return result

    def _post_dashscope(self, path: str, payload: dict[str, Any], extra_headers: dict[str, str] | None = None):
        return self._post(
            path, payload, headers=self._dashscope_headers(extra_headers), base_url=self._dashscope_base_url()
        )

    def _get_dashscope(self, path: str):
        return self._get(path, headers=self._dashscope_headers(), base_url=self._dashscope_base_url())

    def _poll_bailian_task(self, task_id: str):
        interval = _float_config(self.extra_config.get("image_poll_interval_seconds"), 2.0)
        timeout = _float_config(self.extra_config.get("image_poll_timeout_seconds"), 180.0)
        deadline = time.monotonic() + timeout
        while True:
            data, response = self._get_dashscope(f"/tasks/{task_id}")
            status_value = str((data.get("output") or {}).get("task_status") or data.get("task_status") or "").upper()
            if status_value in {"SUCCEEDED", "SUCCESS"}:
                return data, response
            if status_value in {"FAILED", "CANCELED", "CANCELLED", "UNKNOWN"}:
                message = (
                    (data.get("output") or {}).get("message")
                    or data.get("message")
                    or f"百炼生图任务失败: {status_value}"
                )
                raise UpstreamApiError(
                    f"{message} (taskId: {task_id})", request_id=_bailian_request_id(response.headers) or task_id
                )
            if time.monotonic() >= deadline:
                raise UpstreamApiError(
                    f"百炼生图任务轮询超时 (taskId: {task_id})",
                    request_id=_bailian_request_id(response.headers) or task_id,
                )
            time.sleep(interval)

    def _dashscope_base_url(self) -> str:
        return str(self.extra_config.get("dashscope_base_url") or "https://dashscope.aliyuncs.com/api/v1").rstrip("/")

    def _dashscope_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = self._headers()
        workspace_id = self.extra_config.get("workspace_id")
        if workspace_id:
            headers["X-DashScope-WorkSpace"] = str(workspace_id)
        if extra_headers:
            headers.update(extra_headers)
        return headers


class DeepSeekAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.deepseek.com"


class VolcengineArkAdapter(OpenAIHttpAdapter):
    default_base_url = "https://ark.cn-beijing.volces.com/api/v3"

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        normalized_options = _normalize_volcengine_image_options(model, options or {})
        image = normalized_options.pop("image", None)
        payload = {
            "model": model,
            "prompt": prompt,
            "response_format": "url",
            "sequential_image_generation": "disabled",
            **normalized_options,
        }
        if image:
            payload["image"] = image
        data, response = self._post(self.images_path, payload)
        return {
            "data": _normalize_volcengine_image_data(data),
            "raw": data,
            "usage": normalize_usage(data.get("usage")),
            "requestId": response.headers.get("x-request-id") or response.headers.get("x-tt-logid"),
        }


class HunyuanAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.hunyuan.cloud.tencent.com/v1"


class QianfanAdapter(OpenAIHttpAdapter):
    default_base_url = "https://qianfan.baidubce.com/v2"

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        normalized_options = dict(options or {})
        model_lower = model.lower()

        if model_lower == "irag-1.0":
            if len(prompt) > 220:
                logger.warning(
                    f"Model {model} only supports prompt length <= 220. Automatically truncating prompt.",
                    extra={"model": model, "original_length": len(prompt)},
                )
                prompt = prompt[:220]
            normalized_options.pop("negative_prompt", None)
            normalized_options.pop("negativePrompt", None)
            normalized_options.pop("seed", None)
            image_url = normalized_options.pop("image", None)
            if image_url:
                # 百度智能云千帆大模型平台官方 V2 API 规定：ERNIE iRAG 图生图参考图字段名为 refer_image
                normalized_options["refer_image"] = image_url
        else:
            # 百度千帆 V2 API 的其它模型（如 ernie-image-turbo、FLUX.1-schnell 等）目前在千帆平台官方协议中均不支持图生图参考图功能。
            # 后续若有其它千帆模型支持图生图，可在此处扩展入参映射（例如 refer_image 等字段的注入）。
            normalized_options.pop("image", None)
            normalized_options.pop("refer_image", None)

        data, response = self._post(self.images_path, {"model": model, "prompt": prompt, **normalized_options})
        return openai_image_result(data, response)


class ZhipuAdapter(OpenAIHttpAdapter):
    default_base_url = "https://open.bigmodel.cn/api/paas/v4"


class MiniMaxAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.minimax.chat/v1"


class MimoAdapter(OpenAIHttpAdapter):
    default_base_url = ""

    def test(self) -> dict:
        if not self.base_url:
            return {"success": False, "message": "小米 MiMo 尚未配置稳定公开 API baseUrl，请在厂商配置中补充"}
        return super().test()


ADAPTERS = {
    "openai-compatible": OpenAICompatibleAdapter,
    "ollama": OllamaAdapter,
    "gemini": GeminiAdapter,
    "claude": ClaudeAdapter,
    "deepseek": DeepSeekAdapter,
    "volcengine-ark": VolcengineArkAdapter,
    "bailian": BailianAdapter,
    "hunyuan": HunyuanAdapter,
    "qianfan": QianfanAdapter,
    "zhipu": ZhipuAdapter,
    "minimax": MiniMaxAdapter,
    "mimo": MimoAdapter,
}


def build_adapter(provider: AiProvider):
    adapter_cls = ADAPTERS.get(provider.adapter)
    if adapter_cls is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的模型厂商适配器")
    return adapter_cls(provider)


def _resolve_bailian_image_protocol(model: str, options: dict[str, Any]) -> str:
    explicit = options.pop("image_protocol", None) or options.pop("protocol", None)
    if explicit in {"wan2.6-sync", "wan2.6-async", "legacy-async", "wan-legacy-async"}:
        return "legacy-async" if explicit == "wan-legacy-async" else str(explicit)
    async_flag = options.pop("async", None)
    model_key = model.lower().replace("_", "-")
    if model_key.startswith("wan2.6-"):
        return "wan2.6-async" if async_flag is True else "wan2.6-sync"
    if model_key.startswith("qwen-image"):
        # 根据阿里百炼官方文档，qwen-image 系列同步生图接口统一走 /services/aigc/multimodal-generation/generation Endpoint，协议与 wan2.6-sync 完全一致
        return "wan2.6-sync"
    return "legacy-async"


def _build_bailian_wan26_sync_payload(model: str, prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    options = dict(options)
    neg_prompt = _bailian_negative_prompt(options)
    image = options.pop("image", None)

    is_wan26 = model.lower().replace("_", "-").startswith("wan2.6")
    if neg_prompt and is_wan26:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="百炼 wan2.6 同步生图暂不支持 negative_prompt，请启用异步或使用支持负向提示词的模型",
        )

    parameters = _bailian_image_parameters(options)
    if neg_prompt and not is_wan26:
        parameters["negative_prompt"] = neg_prompt

    content = []
    if image:
        if isinstance(image, list):
            for img in image:
                if img:
                    content.append({"image": img})
        elif isinstance(image, str) and image:
            content.append({"image": image})

    content.append({"text": prompt})

    return {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        "parameters": parameters,
    }


def _build_bailian_wan26_async_payload(model: str, prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    input_payload: dict[str, Any] = {"prompt": prompt}
    negative_prompt = _bailian_negative_prompt(options)
    if negative_prompt:
        input_payload["negative_prompt"] = negative_prompt
    return {
        "model": model,
        "input": input_payload,
        "parameters": _bailian_image_parameters(options),
    }


def _build_bailian_legacy_image_payload(model: str, prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    parameters = _bailian_image_parameters(options)
    input_payload: dict[str, Any] = {"prompt": prompt}
    negative_prompt = _bailian_negative_prompt(options)
    if negative_prompt:
        input_payload["negative_prompt"] = negative_prompt
    return {"model": model, "input": input_payload, "parameters": parameters}


def _bailian_negative_prompt(options: dict[str, Any]) -> Any:
    for key in ("negative_prompt", "negativePrompt"):
        value = options.get(key)
        if value is not None and value != "":
            return value
    return None


def _bailian_image_parameters(options: dict[str, Any]) -> dict[str, Any]:
    excluded = {"negative_prompt", "negativePrompt", "async", "image_protocol", "protocol"}
    parameters = {key: value for key, value in options.items() if key not in excluded and value is not None}
    if "size" in parameters:
        parameters["size"] = _normalize_bailian_image_size(parameters["size"])
    return parameters


def _normalize_bailian_image_size(value: Any) -> Any:
    if isinstance(value, str) and "x" in value and "*" not in value:
        return value.lower().replace("x", "*")
    return value


def _extract_bailian_task_id(data: dict[str, Any]) -> str | None:
    output = data.get("output") if isinstance(data, dict) else None
    if isinstance(output, dict):
        task_id = output.get("task_id") or output.get("taskId")
        if task_id:
            return str(task_id)
    task_id = data.get("task_id") or data.get("taskId")
    return str(task_id) if task_id else None


def _bailian_image_result(data: dict[str, Any], request_id: str | None = None) -> dict:
    return {
        "data": _normalize_bailian_image_data(data),
        "raw": data,
        "usage": normalize_usage(data.get("usage")),
        "requestId": request_id,
    }


def _normalize_bailian_image_data(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    normalized: list[dict[str, Any]] = []
    _collect_bailian_images(data, normalized)
    return normalized


def _collect_bailian_images(value: Any, result: list[dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_bailian_images(item, result)
        return
    if not isinstance(value, dict):
        return

    image = value.get("image")
    if image:
        result.append(_normalize_image_item(image))
    item = _normalize_image_item(value)
    if item:
        result.append(item)

    for key in ("data", "results", "output", "choices", "message", "content"):
        child = value.get(key)
        if child is not None:
            _collect_bailian_images(child, result)


def _bailian_request_id(headers) -> str | None:
    return headers.get("x-request-id") or headers.get("x-dashscope-request-id") or headers.get("X-Request-Id")


def _float_config(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_volcengine_image_options(model: str, options: dict[str, Any]) -> dict[str, Any]:
    data = dict(options)
    model_key = model.replace(".", "-")
    if "seedream-4-5" in model_key or "seedream-4-0" in model_key:
        size = data.get("size")
        if size == "1K":
            data["size"] = "1024x1024"
        elif size == "2K":
            data["size"] = "2048x2048"
        elif size == "4K":
            data["size"] = "4096x4096"
        _validate_seedream_4_size(data.get("size"))
        data.pop("guidance_scale", None)
    return data


def _validate_seedream_4_size(size: Any) -> None:
    if not isinstance(size, str) or "x" not in size:
        return

    try:
        width_text, height_text = size.lower().split("x", 1)
        pixels = int(width_text) * int(height_text)
    except (TypeError, ValueError):
        return

    if pixels < 3_686_400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="火山 Seedream 4.x 图片尺寸至少需要 3686400 像素，请使用 2560x1440、1440x2560、2048x2048 或更高分辨率",
        )


def _normalize_volcengine_image_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("data"), list):
        return data["data"]

    images = data.get("images")
    if isinstance(images, list):
        return [_normalize_image_item(item) for item in images]

    result = data.get("result")
    if isinstance(result, dict):
        nested = _normalize_volcengine_image_data(result)
        if nested:
            return nested
    if isinstance(result, list):
        return [_normalize_image_item(item) for item in result]

    item = _normalize_image_item(data)
    return [item] if item else []


def _normalize_image_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"url": item}
    if not isinstance(item, dict):
        return {}

    url = item.get("url") or item.get("image_url") or item.get("imageUrl")
    b64_json = item.get("b64_json") or item.get("b64Json") or item.get("base64")
    normalized: dict[str, Any] = dict(item)
    if url:
        normalized["url"] = url
    if b64_json:
        normalized["b64_json"] = b64_json
    return normalized if ("url" in normalized or "b64_json" in normalized) else {}
