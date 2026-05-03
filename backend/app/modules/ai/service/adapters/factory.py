from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.base import normalize_usage
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter


class BailianAdapter(OpenAIHttpAdapter):
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class DeepSeekAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.deepseek.com"


class VolcengineArkAdapter(OpenAIHttpAdapter):
    default_base_url = "https://ark.cn-beijing.volces.com/api/v3"

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        normalized_options = _normalize_volcengine_image_options(model, options or {})
        payload = {
            "model": model,
            "prompt": prompt,
            "response_format": "url",
            "sequential_image_generation": "disabled",
            **normalized_options,
        }
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
