from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from app.core.secret import decrypt_secret
from app.modules.ai.constants import AI_ADAPTERS
from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.bailian_openapi import list_workspace_authorized_models
from app.modules.ai.service.adapters.base import (
    AdapterInputError,
    UpstreamApiError,
    normalize_usage,
    openai_image_result,
)
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter
from app.modules.ai.service.adapters.poryf import PoryfAdapter
from app.modules.ai.service.adapters.size_utils import parse_pixel_size
from app.modules.ai.service.adapters.toapis import ToApisAdapter
from app.modules.ai.service.adapters.volcengine_openapi import iter_ark_available_models


class BailianAdapter(OpenAIHttpAdapter):
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def list_models(self) -> list[dict[str, Any]]:
        # compatible-mode /models 返回的是平台模型全集；业务空间已授权视角走 maas 权限接口
        workspace_id = str(self.extra_config.get("workspace_id") or "").strip()
        if not workspace_id:
            raise UpstreamApiError("百炼模型同步需要业务空间 ID，请在扩展配置中填写 workspace_id")
        if not self.api_key:
            raise UpstreamApiError("百炼模型同步需要 API Key，请先在厂商配置中填写")
        return list_workspace_authorized_models(api_key=self.api_key, workspace_id=workspace_id, timeout=self.timeout)

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


def _adapt_deepseek_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """DeepSeek chat/completions 的两项结构化输出适配：

    1. JSON Output 仅支持 response_format=json_object，不支持 json_schema
       （返回 400 "This response_format type is unavailable now"）。json_schema 降级为
       json_object；schema 结构信息由调用方 prompt 中的格式指令兜底（如工作流 LLM 节点
       会追加 jsonFields 结构描述）。
    2. V4 思考模型的思维链与正文共享 max_tokens，JSON 模式下小预算会导致 content 为空
       （官方已知问题）。结构化输出场景思维链无消费方，注入 thinking=disabled 保证正文
       直接产出；调用方显式设置 thinking 时尊重其选择。旧模型名（deepseek-chat 等）
       安全接受该参数，已实测。
    """
    normalized = dict(options or {})
    response_format = normalized.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
        normalized["response_format"] = {"type": "json_object"}
    if normalized.get("response_format") == {"type": "json_object"} and "thinking" not in normalized:
        normalized["thinking"] = {"type": "disabled"}
    return normalized


class DeepSeekAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.deepseek.com"

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        return super().chat(model=model, messages=messages, options=_adapt_deepseek_options(options))

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        return super().stream_chat(model=model, messages=messages, options=_adapt_deepseek_options(options))


class VolcengineArkAdapter(OpenAIHttpAdapter):
    default_base_url = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(self, provider: AiProvider):
        super().__init__(provider)
        # AI-017 实例池：管理密钥初始化期物化，禁止方法内惰性访问 ORM 实体（detached 即炸）
        self.admin_access_key = decrypt_secret(provider.admin_access_key_cipher)
        self.admin_secret_key = decrypt_secret(provider.admin_secret_key_cipher)

    def list_models(self) -> list[dict[str, Any]]:
        # 方舟推理域名不提供 OpenAI 风格 /models；模型开通列表走火山 OpenAPI（AK/SK V4 签名）
        if not self.admin_access_key or not self.admin_secret_key:
            raise UpstreamApiError(
                "火山方舟模型列表仅支持 Access Key 鉴权，请先在厂商配置中填写管理 Access Key/Secret Key"
            )
        return iter_ark_available_models(
            access_key=self.admin_access_key, secret_key=self.admin_secret_key, timeout=self.timeout
        )

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
    "toapis": ToApisAdapter,
    "poryf": PoryfAdapter,
}

# 单一权威一致性校验（AI-010）：实现映射与 constants.AI_ADAPTERS 漂移即 import 失败，
# 新增厂商漏改任何一侧都在启动期暴露，而非运行期 400
if set(ADAPTERS) != AI_ADAPTERS:
    raise RuntimeError(f"ADAPTERS 实现与 constants.AI_ADAPTERS 不一致: {set(ADAPTERS) ^ set(AI_ADAPTERS)}（AI-010）")


# 适配器实例池（AI-017）：适配器全部状态都是初始化期只读配置（api_key/base_url/
# extra_config 派生字段，含 OpenAI SDK client），无请求级可变状态，可安全跨请求复用；
# 免去每次调用重建 SDK client / 重新解密密钥的开销。键 = 配置全量指纹，配置变更自然失效。
_ADAPTER_CACHE: dict[tuple, Any] = {}
_ADAPTER_CACHE_MAX = 256


def build_adapter(provider: AiProvider):
    cache_key = (
        provider.id,
        provider.adapter,
        provider.base_url or "",
        provider.api_key_cipher or "",
        provider.extra_config or "",
        # 管理密钥参与指纹：ark 等适配器在初始化期物化 admin AK/SK（list_models 用），
        # 不入键则改密后旧凭证复用至进程重启；其余 provider 恒 None 不影响区分度
        provider.admin_access_key_cipher or "",
        provider.admin_secret_key_cipher or "",
    )
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    adapter_cls = ADAPTERS.get(provider.adapter)
    if adapter_cls is None:
        # 配置错误不是上游故障：不降级（掩盖配置问题），直接 4xx 显性暴露（AI-009）
        raise AdapterInputError(f"不支持的模型厂商适配器: {provider.adapter}")
    adapter = adapter_cls(provider)
    # 键空间 = 历史配置组合数，变更低频；上限防御异常刷写场景，超限后退化为每次新建
    if len(_ADAPTER_CACHE) < _ADAPTER_CACHE_MAX:
        _ADAPTER_CACHE[cache_key] = adapter
    return adapter


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
        # 参数组合错误：换模型重跑结果相同，抛 AdapterInputError 阻断降级二次计费（AI-009）
        raise AdapterInputError(
            "百炼 wan2.6 同步生图暂不支持 negative_prompt，请启用异步或使用支持负向提示词的模型",
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
    """百炼兼容模式要求 ``宽*高`` 写法，这里把任意分隔符写法统一过来。

    旧实现用 ``"x" in value`` 判定，全角 ``864×1152`` 命中失败会被原样透传给上游。
    """
    parsed = parse_pixel_size(value)
    if parsed is not None:
        return f"{parsed[0]}*{parsed[1]}"
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
    """校验 Seedream 4.x 的最小像素约束。

    非像素尺寸（档位别名等）不在此处校验，交给上游判断。
    必须按归一化后的值判定，否则全角写法会静默绕过这道校验。
    """
    parsed = parse_pixel_size(size)
    if parsed is None:
        return

    pixels = parsed[0] * parsed[1]
    if pixels < 3_686_400:
        # 参数错误：同上，阻断降级二次计费（AI-009）
        raise AdapterInputError(
            "火山 Seedream 4.x 图片尺寸至少需要 3686400 像素，请使用 2560x1440、1440x2560、2048x2048 或更高分辨率",
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
