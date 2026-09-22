from __future__ import annotations

import logging
import math
import time
from typing import Any

import httpx

from app.modules.ai.service.adapters.base import UpstreamApiError, normalize_usage
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter
from app.modules.ai.service.adapters.size_utils import (
    ensure_pixel_size,
    normalize_size_token,
    parse_pixel_size,
)

logger = logging.getLogger(__name__)

DEFAULT_TOAPIS_BASE_URL = "https://api.toapis.cn"
DEFAULT_TOAPIS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 常见比例表 (w, h, ratio_str)
STANDARD_RATIOS = [
    (1, 1, "1:1"),
    (16, 9, "16:9"),
    (9, 16, "9:16"),
    (4, 3, "4:3"),
    (3, 4, "3:4"),
    (3, 2, "3:2"),
    (2, 3, "2:3"),
]


# 尺寸归一化与校验统一走 size_utils，勿在此处自行写字符判断。
# 历史事故：旧实现用 `"x" in str(size)` 判定，全角 `864×1152` 命中失败后被静默
# 回落成 1024x1024，全程无日志，问题隐藏一整天。详见 size_utils 模块说明。


def _float_config(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_toapis_edition(model: str) -> str:
    """根据模型名判断版本：vip / official / normal"""
    model_lower = (model or "").lower().strip()
    if model_lower.endswith("-vip") or ":vip" in model_lower:
        return "vip"
    if model_lower.endswith("-official") or ":official" in model_lower:
        return "official"
    return "normal"


def _convert_pixel_size_to_ratio_and_resolution(size_val: str | None) -> tuple[str, str]:
    """把尺寸换算为最接近的比例与分辨率档位。

    入参可以是标准比例（``3:4``）或像素尺寸（``1024x1024``，分隔符容错）；
    未提供走默认；两者都不是则抛 UpstreamApiError（不再静默回落成 1:1 + 1K）。
    """
    normalized = normalize_size_token(size_val)
    if normalized is None:
        return "1:1", "1K"

    # 本身已经是标准比例
    for _, _, ratio in STANDARD_RATIOS:
        if normalized == ratio:
            return ratio, "1K"

    parsed = parse_pixel_size(normalized)
    if parsed is None:
        raise UpstreamApiError(
            "ToAPIs 普通版尺寸参数非法：%r（归一化后为 %r）。仅接受标准比例"
            "（1:1 / 16:9 / 9:16 / 4:3 / 3:4 / 3:2 / 2:3）或像素尺寸（如 1024x1024）。"
            % (size_val, normalized)
        )

    w, h = parsed
    target_aspect = w / h
    best_ratio = "1:1"
    min_diff = float("inf")
    for rw, rh, rstr in STANDARD_RATIOS:
        diff = abs(target_aspect - (rw / rh))
        if diff < min_diff:
            min_diff = diff
            best_ratio = rstr

    # 推断 resolution 档位
    pixels = w * h
    if pixels >= 3840 * 2160 * 0.8:
        resolution = "4K"
    elif pixels >= 1920 * 1080 * 0.8:
        resolution = "2K"
    else:
        resolution = "1K"

    return best_ratio, resolution


class ToApisAdapter(OpenAIHttpAdapter):
    """
    ToAPIs 适配器（专用于 GPT-Image-2.5 三版本接入）。
    支持普通版、VIP版、Official版异步生图任务提交与轮询。
    """

    default_base_url = DEFAULT_TOAPIS_BASE_URL
    images_generations_path = "/v1/images/generations"
    images_edits_path = "/v1/images/edits"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        # 注入标准浏览器 UA，避免 Cloudflare 拦截
        headers["User-Agent"] = self.extra_config.get("user_agent") or DEFAULT_TOAPIS_UA
        return headers

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        options = dict(options or {})
        edition = _resolve_toapis_edition(model)

        image_input = options.pop("image", None)
        size = options.pop("size", None)
        quality = options.pop("quality", None)
        resolution = options.pop("resolution", None)
        background = options.pop("background", None)

        # 统一处理参考图 URL 列表
        image_urls: list[str] = []
        if image_input:
            if isinstance(image_input, list):
                image_urls = [str(u) for u in image_input if u]
            elif isinstance(image_input, str) and image_input:
                image_urls = [image_input]

        # 易错字符显式告警：全角乘号等字符会被归一化纠正，但必须留下痕迹。
        # 本次事故的根因就是"静默纠正"——值被换掉了，却没有任何日志可查。
        if size is not None:
            normalized_size = normalize_size_token(size)
            raw_size = str(size).strip().lower()
            if normalized_size is not None and normalized_size != raw_size:
                logger.warning(
                    "ToAPIs 尺寸入参含易错字符，已自动归一化：%r -> %r",
                    size,
                    normalized_size,
                    extra={"original_size": str(size), "normalized_size": normalized_size, "model": model},
                )

        if edition == "normal":
            # 普通版：比例 + resolution，固定 high（忽略 quality 避免误解）
            ratio, inferred_res = _convert_pixel_size_to_ratio_and_resolution(size)
            final_res = resolution or inferred_res or "1K"
            normalized_size = normalize_size_token(size)
            if normalized_size and normalized_size != ratio:
                logger.info(
                    "ToAPIs 普通版已将输入尺寸 %s 自动转换为比例 %s 与分辨率 %s",
                    normalized_size,
                    ratio,
                    final_res,
                    extra={
                        "original_size": size,
                        "normalized_size": normalized_size,
                        "converted_ratio": ratio,
                        "resolution": final_res,
                    },
                )
            payload: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "size": ratio,
                "resolution": final_res,
                "n": 1,
                **options,
            }
            if image_urls:
                payload["reference_images"] = image_urls
            if background:
                payload["background"] = background
            data, response = self._post(self.images_generations_path, payload)

        elif edition == "official":
            # Official 版：像素尺寸 + 5档 quality + image_urls
            final_size = ensure_pixel_size(size)
            payload = {
                "model": model,
                "prompt": prompt,
                "size": final_size,
                "n": 1,
                **options,
            }
            if quality:
                payload["quality"] = quality
            if image_urls:
                payload["image_urls"] = image_urls
            if background:
                payload["background"] = background
            data, response = self._post(self.images_generations_path, payload)

        else:
            # VIP 版：无图生图走 generations，有图生图走 edits multipart
            final_size = ensure_pixel_size(size)
            if image_urls:
                # VIP 图生图: POST /v1/images/edits multipart/form-data
                form_fields: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "size": final_size,
                    "n": "1",
                }
                if quality:
                    form_fields["quality"] = quality
                if background:
                    form_fields["background"] = background
                for k, v in options.items():
                    if v is not None:
                        form_fields[k] = str(v)

                data, response = self._post_vip_edits_multipart(
                    fields=form_fields,
                    image_url=image_urls[0],
                )
            else:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "size": final_size,
                    "n": 1,
                    **options,
                }
                if quality:
                    payload["quality"] = quality
                if background:
                    payload["background"] = background
                data, response = self._post(self.images_generations_path, payload)

        task_id = self._extract_task_id(data)
        if not task_id:
            raise UpstreamApiError(
                "ToAPIs 生图任务创建失败: 响应缺少 task_id",
                request_id=response.headers.get("x-request-id"),
            )

        final_data, final_response = self._poll_toapis_task(task_id)
        return self._normalize_toapis_result(final_data, task_id)

    def _post_vip_edits_multipart(
        self,
        fields: dict[str, Any],
        image_url: str,
    ) -> tuple[dict, httpx.Response]:
        """以 multipart/form-data 方式提交 VIP 版 edits 任务"""
        headers = self._headers()
        # 移除 Content-Type，由 httpx 自动生成包含 boundary 的 multipart 头
        headers.pop("Content-Type", None)
        headers.pop("content-type", None)

        url = f"{self.base_url.rstrip('/')}{self.images_edits_path}"
        # ToAPIs 接受 image 字段放公网 URL，使用 files 传 tuple (None, image_url) 即可构造 multipart 字段
        files = {"image": (None, image_url)}
        response = httpx.post(
            url,
            data=fields,
            files=files,
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(response)
        return response.json(), response

    def _extract_task_id(self, data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return None
        task_id = data.get("id") or data.get("task_id") or data.get("taskId")
        return str(task_id) if task_id else None

    def _poll_toapis_task(self, task_id: str) -> tuple[dict, httpx.Response]:
        interval = _float_config(self.extra_config.get("image_poll_interval_seconds"), 3.0)
        timeout = _float_config(self.extra_config.get("image_poll_timeout_seconds"), 600.0)
        deadline = time.monotonic() + timeout

        while True:
            data, response = self._get(f"{self.images_generations_path}/{task_id}")
            status_value = str(data.get("status") or "").lower()

            if status_value == "completed":
                return data, response

            if status_value in {"failed", "error", "cancelled", "canceled"}:
                err = data.get("error")
                err_msg = json_str(err) if isinstance(err, (dict, list)) else str(err or f"任务状态: {status_value}")
                raise UpstreamApiError(
                    f"ToAPIs 生图任务失败: {err_msg} (taskId: {task_id})",
                    request_id=task_id,
                )

            if time.monotonic() >= deadline:
                raise UpstreamApiError(
                    f"ToAPIs 生图任务轮询超时 (taskId: {task_id})",
                    request_id=task_id,
                )

            time.sleep(interval)

    def _normalize_toapis_result(self, data: dict[str, Any], task_id: str) -> dict:
        result_node = data.get("result") or {}
        items = result_node.get("data") or data.get("data") or []

        url: str | None = None
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                url = first.get("url") or first.get("image_url")
            elif isinstance(first, str):
                url = first
        elif isinstance(items, dict):
            url = items.get("url")
        elif isinstance(items, str):
            url = items

        normalized_data = [{"url": url}] if url else []
        usage = data.get("usage") or result_node.get("usage") or {}

        return {
            "data": normalized_data,
            "raw": data,
            "usage": normalize_usage(usage),
            "requestId": task_id,
            "taskId": task_id,
        }

    def test(self) -> dict:
        try:
            data, _ = self._get(self.models_path)
            return {"success": True, "count": len(data.get("data", data.get("models", [])))}
        except Exception:
            if self.extra_config.get("skip_model_list_check", True):
                return {"success": True, "message": "ToAPIs 适配器已就绪（跳过模型列表探测）"}
            raise


def json_str(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
