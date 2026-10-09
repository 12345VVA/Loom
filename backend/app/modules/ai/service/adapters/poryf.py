from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.framework.url_security import safe_stream, validate_remote_url
from app.modules.ai.service.adapters.base import UpstreamApiError, openai_image_result
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter
from app.modules.ai.service.adapters.size_utils import ensure_pixel_size, parse_pixel_size

logger = logging.getLogger(__name__)

DEFAULT_PORYF_BASE_URL = "https://token.poryf.com/v1"

# 同步生图实测 21s ~ 196s 波动（同参数同模型波动 9 倍），官方建议超时 ≥5 分钟
DEFAULT_PORYF_TIMEOUT_SECONDS = 300.0

# 官方支持的最大边长 3840px（4K）
PORYF_MAX_IMAGE_EDGE = 3840

# 官方画质五档；flare / sunburst 同代同价
PORYF_IMAGE_QUALITIES = {"low", "medium", "high", "xhigh", "max"}

PORYF_OUTPUT_FORMATS = {"png", "jpeg"}

# 实测参考图 >1MB 会 500 且空跑 283s 才返回（JSON URL 模式 2.8MB 必失败 / multipart 1MB 正常），
# 本地预检直接拒绝，错误信息远比上游死亡行军友好
DEFAULT_PORYF_EDIT_REFERENCE_MAX_BYTES = 1_048_576

_PORYF_IMAGE_ALLOWED_OPTION_KEYS = {"size", "quality", "output_format", "n"}

_REFERENCE_DOWNLOAD_TIMEOUT = 15


class PoryfAdapter(OpenAIHttpAdapter):
    """Poryf（再来点Token）适配器。

    OpenAI 兼容网关，同步返回（无任务 ID、无轮询），按 token 计费且无幂等键：
    - 超时必须 ≥300s，且绝不自动重试（超时重试=重复扣费）；httpx 实现天然无 SDK 隐性重试。
    - 文生图 POST /images/generations；图片编辑 POST /images/edits（multipart 实测通过，
      本适配器统一下载参考图后 multipart 上传，不依赖网关回源抓内网地址）。
    - 响应只有 b64_json（无 url），不要发送 response_format（实测请求从未带过该参数，
      网关对未知字段有严格校验迹象）。
    - 错误判别看 HTTP 状态码，网关对 400/500 一律返回相同 error.type。
    """

    default_base_url = DEFAULT_PORYF_BASE_URL
    images_generations_path = "/images/generations"
    images_edits_path = "/images/edits"

    def __init__(self, provider):
        super().__init__(provider)
        # BaseHttpAdapter 默认 60s，对同步生图远远不够；厂商级显式配置优先
        if "timeout" not in self.extra_config:
            self.timeout = DEFAULT_PORYF_TIMEOUT_SECONDS
        self.edit_reference_max_bytes = int(
            self.extra_config.get("edit_reference_max_bytes", DEFAULT_PORYF_EDIT_REFERENCE_MAX_BYTES)
        )

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        options = dict(options or {})

        image_input = options.pop("image", None)
        allowed_options = {k: v for k, v in options.items() if k in _PORYF_IMAGE_ALLOWED_OPTION_KEYS}
        dropped_options = {k: v for k, v in options.items() if k not in _PORYF_IMAGE_ALLOWED_OPTION_KEYS}
        if dropped_options:
            # response_format 故意不在白名单：Poryf 默认回 b64_json，多传反而可能被网关字段校验拒绝
            logger.warning(
                "Poryf 生图参数已拦截非标准字段",
                extra={
                    "provider_code": self.provider.code,
                    "model": model,
                    "dropped_option_keys": sorted(dropped_options.keys()),
                },
            )

        image_urls = _normalize_reference_images(image_input)
        if len(image_urls) > 1:
            logger.warning(
                "Poryf 图片编辑当前仅支持单张参考图，已忽略多余项",
                extra={"provider_code": self.provider.code, "model": model, "image_count": len(image_urls)},
            )

        payload: dict[str, Any] = {"model": model, "prompt": prompt}

        n_value = allowed_options.get("n")
        if isinstance(n_value, int) and n_value > 1:
            logger.warning(
                "Poryf 生图仅支持 n=1，已自动截断",
                extra={"provider_code": self.provider.code, "model": model, "original_n": n_value},
            )
        # n 不上行：Poryf 默认即单图

        size = allowed_options.get("size")
        if size is not None and size != "":
            payload["size"] = self._validate_size(size)

        quality = allowed_options.get("quality")
        if quality is not None and quality != "":
            if str(quality) not in PORYF_IMAGE_QUALITIES:
                raise UpstreamApiError(
                    f"Poryf 画质参数非法：{quality!r}，仅支持 {'/'.join(sorted(PORYF_IMAGE_QUALITIES))}"
                )
            payload["quality"] = quality

        output_format = allowed_options.get("output_format")
        if output_format is not None and output_format != "":
            if str(output_format) not in PORYF_OUTPUT_FORMATS:
                raise UpstreamApiError(
                    f"Poryf 输出格式非法：{output_format!r}，仅支持 {'/'.join(sorted(PORYF_OUTPUT_FORMATS))}"
                )
            payload["output_format"] = output_format

        if image_urls:
            content, filename, content_type = self._load_reference_image(image_urls[0])
            data, response = self._post_edits_multipart(
                fields={key: str(value) for key, value in payload.items()},
                files={"image": (filename, content, content_type)},
            )
        else:
            data, response = self._post(self.images_generations_path, payload)
        return openai_image_result(data, response)

    def _validate_size(self, value: Any) -> str:
        # 比例（1:1）等非像素写法显式报错，不做静默回落；全角乘号等由 size_utils 归一
        normalized = ensure_pixel_size(value, label="Poryf")
        parsed = parse_pixel_size(normalized)
        if parsed and max(parsed) > PORYF_MAX_IMAGE_EDGE:
            raise UpstreamApiError(f"Poryf 图片尺寸最大边长 {PORYF_MAX_IMAGE_EDGE}px，{normalized} 超限，请降低分辨率")
        return normalized

    def _load_reference_image(self, url: str) -> tuple[bytes, str, str]:
        """下载/解码参考图，返回 (内容, 文件名, MIME 类型)。

        data: URL 直接解码；本站地址直连回源（validate_remote_url 会拒私网/回环，
        而自取本站无 SSRF 风险）；外部地址走 SSRF 防护下载。统一在此做 ≤1MB 预检。
        """
        if url.startswith("data:"):
            return self._decode_data_url(url)
        if _is_own_backend_url(url):
            return self._download_direct(url)
        return self._download_remote(url)

    def _check_reference_size(self, size_bytes: int) -> None:
        if size_bytes > self.edit_reference_max_bytes:
            raise UpstreamApiError(
                f"Poryf 参考图 {size_bytes} 字节超过上限 {self.edit_reference_max_bytes} 字节（约 1MB），"
                "请压缩后重试；超限请求上游会长时间空跑后才失败"
            )

    def _decode_data_url(self, url: str) -> tuple[bytes, str, str]:
        try:
            header, b64_data = url.split(",", 1)
            mime_type = header.split(";", 1)[0].removeprefix("data:")
            if not mime_type.startswith("image/"):
                mime_type = "image/png"
        except ValueError as exc:
            raise UpstreamApiError("Poryf 参考图 data URL 格式非法") from exc
        try:
            content = base64.b64decode(b64_data)
        except Exception as exc:
            raise UpstreamApiError("Poryf 参考图 data URL base64 解码失败") from exc
        self._check_reference_size(len(content))
        return content, _filename_from_mime(mime_type), mime_type

    def _download_direct(self, url: str) -> tuple[bytes, str, str]:
        """本站地址直连下载（不经 SSRF 校验——目标是自家后端）。"""
        try:
            response = httpx.get(url, timeout=_REFERENCE_DOWNLOAD_TIMEOUT, follow_redirects=False)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamApiError(f"Poryf 参考图下载失败（本站回源）: {url}: {exc}") from exc
        content = response.content
        self._check_reference_size(len(content))
        return content, _filename_from_url(url), _normalize_image_mime(response.headers.get("content-type"))

    def _download_remote(self, url: str) -> tuple[bytes, str, str]:
        """外部地址经 SSRF 防护下载（校验协议/IP/DNS 解析，禁止重定向）。"""
        try:
            safe_url, original_host = validate_remote_url(url)
        except ValueError as exc:
            raise UpstreamApiError(f"Poryf 参考图 URL 未通过安全校验: {exc}") from exc
        try:
            with safe_stream(
                "GET", safe_url, original_host, headers={"Host": original_host}, timeout=_REFERENCE_DOWNLOAD_TIMEOUT
            ) as response:
                if response.is_redirect:
                    raise UpstreamApiError("Poryf 参考图 URL 不允许重定向")
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.edit_reference_max_bytes:
                    raise UpstreamApiError(
                        f"Poryf 参考图 Content-Length {content_length} 超过上限 {self.edit_reference_max_bytes} 字节"
                    )
                chunks: list[bytes] = []
                bytes_read = 0
                content_type = _normalize_image_mime(response.headers.get("content-type"))
                for chunk in response.iter_bytes(chunk_size=8192):
                    bytes_read += len(chunk)
                    self._check_reference_size(bytes_read)
                    chunks.append(chunk)
                content = b"".join(chunks)
        except UpstreamApiError:
            raise
        except httpx.HTTPError as exc:
            raise UpstreamApiError(f"Poryf 参考图下载失败: {url}: {exc}") from exc
        return content, _filename_from_url(url), content_type

    def _post_edits_multipart(
        self,
        fields: dict[str, Any],
        files: dict[str, Any],
    ) -> tuple[dict, httpx.Response]:
        """以 multipart/form-data 提交图片编辑（实测通过的推荐传图方式）。"""
        headers = self._headers()
        # 移除 Content-Type，由 httpx 自动生成含 boundary 的 multipart 头
        headers.pop("Content-Type", None)
        headers.pop("content-type", None)
        url = f"{self.base_url.rstrip('/')}{self.images_edits_path}"
        response = httpx.post(url, data=fields, files=files, headers=headers, timeout=self.timeout)
        self._raise_for_status(response)
        return response.json(), response


def _normalize_reference_images(image_input: Any) -> list[str]:
    if isinstance(image_input, list):
        return [str(item) for item in image_input if item]
    if isinstance(image_input, str) and image_input:
        return [image_input]
    return []


def _normalize_netloc(parsed) -> tuple[str, int]:
    default_port = 443 if parsed.scheme == "https" else 80
    return (parsed.hostname or "").lower(), parsed.port or default_port


def _own_backend_netlocs() -> set[tuple[str, int]]:
    """与 runtime_service._make_absolute_url 的 base 候选保持一致：
    BACKEND_URL → EXTERNAL_URL → HOST:PORT 兜底；那边改动时须同步这里。
    """
    bases = [settings.BACKEND_URL, settings.EXTERNAL_URL]
    host = settings.HOST
    if host == "0.0.0.0":
        host = "127.0.0.1"
    bases.append(f"http://{host}:{settings.PORT}")
    result: set[tuple[str, int]] = set()
    for base in bases:
        if not base:
            continue
        parsed = urlparse(str(base))
        if parsed.hostname:
            result.add(_normalize_netloc(parsed))
    return result


def _is_own_backend_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    return _normalize_netloc(parsed) in _own_backend_netlocs()


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    return name or "reference.png"


def _filename_from_mime(mime_type: str) -> str:
    return "reference.jpeg" if "jpeg" in mime_type or "jpg" in mime_type else "reference.png"


def _normalize_image_mime(content_type: str | None) -> str:
    if not content_type:
        return "image/png"
    mime = content_type.split(";", 1)[0].strip().lower()
    return mime if mime.startswith("image/") else "image/png"
