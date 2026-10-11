"""多模态图片取回公共工具（WFI-2b，多模态一期阶段二）。

Claude（base64 source）与 Gemini（inlineData）的 IR → 厂商协议转换都需要
「图片 URL → (mime, base64)」，此处统一承载：

- data URI：直接解析（不产生网络请求）；
- http(s)：全套 SSRF 校验（协议白名单 + 私网/环回/链路本地/云元数据 IP 拦截 +
  DNS 解析结果校验，返回以已校验 IP 为 hostname 的 URL 缓解 rebinding TOCTOU）、
  拒绝重定向、MIME 白名单、大小上限；
- 失败抛 ``UpstreamApiError``——chat 链路绑定的图片取不回应显式失败（用户以为
  模型看了图实则静默丢弃是错误语义），与生图链路 ``_prepare_gemini_image_part``
  的「None 静默跳过」宽松语义刻意区分。

另提供 ``extract_system_text``：system 消息文本提取的多模态防崩版（list content
取 text part 再 join，Claude/Gemini 适配器的 ``"\\n".join`` 对 list 会 TypeError）。
"""

from __future__ import annotations

import base64
from typing import Any

from app.framework.url_security import safe_stream, validate_remote_url
from app.modules.ai.service.adapters.base import UpstreamApiError

MAX_IMAGE_DOWNLOAD_SIZE = 10 * 1024 * 1024  # 10MB，与生图链路 _prepare_gemini_image_part 对齐

# 多模态输入允许的图片 MIME（去掉 ; 参数后比对）
IMAGE_MIME_WHITELIST = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


def parse_data_uri(data_uri: str) -> tuple[str, str]:
    """拆解 data URI 为 (mime, base64)。格式非法抛 UpstreamApiError。"""
    try:
        header, b64_data = data_uri.split(",", 1)
        mime_type = header.split(";")[0].split(":", 1)[1] or "image/png"
        base64.b64decode(b64_data, validate=True)  # 预校验，坏 base64 提前显式失败
        return mime_type, b64_data
    except UpstreamApiError:
        raise
    except Exception as exc:
        raise UpstreamApiError("多模态图片 data URI 格式非法") from exc


def fetch_image_as_data_uri(url: str, *, max_bytes: int = MAX_IMAGE_DOWNLOAD_SIZE) -> str:
    """取回图片并编码为 ``data:<mime>;base64,<b64>``。

    data URI 原样返回（经 parse_data_uri 预校验）；http(s) 经 SSRF 校验下载。
    任何失败（私网拦截/重定向/超限/非图片 MIME/网络错误）抛 UpstreamApiError。
    """
    if not isinstance(url, str) or not url:
        raise UpstreamApiError("多模态图片 URL 为空")
    if url.startswith("data:"):
        mime_type, b64_data = parse_data_uri(url)
        return f"data:{mime_type};base64,{b64_data}"
    if not (url.startswith("http://") or url.startswith("https://")):
        raise UpstreamApiError(f"多模态图片 URL 协议不受支持: {url[:80]}")

    try:
        # SSRF 防护：返回以已校验 IP 为 hostname 的 URL，防 DNS rebinding TOCTOU
        safe_url, original_host = validate_remote_url(url)
        headers = {"Host": original_host}
        with safe_stream("GET", safe_url, original_host, headers=headers, timeout=15, follow_redirects=False) as r:
            if r.is_redirect:
                raise UpstreamApiError("多模态图片 URL 不允许重定向")
            r.raise_for_status()
            content_length = r.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise UpstreamApiError(f"多模态图片超过大小限制: {content_length} bytes")

            chunks = []
            bytes_read = 0
            for chunk in r.iter_bytes(chunk_size=8192):
                bytes_read += len(chunk)
                if bytes_read > max_bytes:
                    raise UpstreamApiError("多模态图片超过大小限制 (10MB)")
                chunks.append(chunk)
            content = b"".join(chunks)

            mime_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            if mime_type not in IMAGE_MIME_WHITELIST:
                raise UpstreamApiError(f"多模态图片 MIME 不在白名单: {mime_type or '未知'}")
            return f"data:{mime_type};base64,{base64.b64encode(content).decode('utf-8')}"
    except UpstreamApiError:
        raise
    except Exception as exc:
        raise UpstreamApiError(f"多模态图片下载失败: {type(exc).__name__}") from exc


def extract_system_text(messages: list[dict[str, Any]]) -> str:
    """system 消息的纯文本提取（多模态防崩版）。

    content 为 list 时取 text part 再 join（Claude/Gemini 适配器的 ``"\\n".join``
    对 list 会直接 TypeError）；str 原样。非 system 角色跳过。
    """
    parts: list[str] = []
    for item in messages:
        if item.get("role") != "system":
            continue
        content = item.get("content", "")
        if isinstance(content, list):
            content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        if isinstance(content, str) and content:
            parts.append(content)
    return "\n".join(parts)
