"""
统一 JSON 响应包装
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.framework.api.error_codes import status_to_error_code
from app.framework.api.response import is_enveloped, ok

SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json")


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 错误响应契约兜底（先于 skip 判定）：4xx/5xx 必须是 error envelope。
        # 非 JSON 错误（网关/代理注入的 text/plain、PlainTextResponse 等）也在此
        # 统一转 envelope，不因 media_type 不符而绕过契约（docs 静态路径除外）。
        if response.status_code >= 400 and not request.url.path.startswith(SKIP_PREFIXES):
            return await _normalize_error_response(response)

        if _should_skip(request, response):
            return response

        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > settings.RESPONSE_ENVELOPE_MAX_BYTES:
            return response

        raw_body = b""
        body_too_large = False
        async for chunk in response.body_iterator:
            raw_body += chunk
            if len(raw_body) > settings.RESPONSE_ENVELOPE_MAX_BYTES:
                body_too_large = True

        if body_too_large:
            return Response(
                content=raw_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if not raw_body:
            payload = None
        else:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                return Response(
                    content=raw_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

        # 错误响应契约兜底：4xx/5xx 必须是 error envelope（code≠1000）。历史上
        # starlette Router 的裸 {"detail": ...}（未被 handler 接管的 404/405 等）
        # 会被 ok() 误包成 code=1000 success——在这里统一转为 error envelope。
        if response.status_code >= 400:
            if is_enveloped(payload) and payload.get("code") != 1000:
                content = payload
            else:
                detail = payload.get("detail") if isinstance(payload, dict) else payload
                content = {
                    "code": status_to_error_code(response.status_code),
                    "message": str(detail) if detail is not None else f"请求失败（HTTP {response.status_code}）",
                    "data": None,
                }
        elif is_enveloped(payload):
            content = payload
        else:
            content = ok(_normalize_payload(payload))

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return JSONResponse(
            status_code=response.status_code,
            content=content,
            headers=headers,
        )


def _should_skip(request: Request, response: Response) -> bool:
    if request.url.path.startswith(SKIP_PREFIXES):
        return True
    media_type = response.media_type or response.headers.get("content-type", "")
    if "application/json" not in media_type:
        return True
    return False


async def _normalize_error_response(response: Response) -> Response:
    """把任意形态的错误响应规范为 error envelope。

    - 已是 envelope 且 code≠1000：原样透传（信任 handler/守卫层）；
    - JSON 裸形态（{"detail": ...}、code=1000 误标等）：转 error envelope；
    - 非 JSON（text/plain 等）：原文截断作为 message，media_type 归一 JSON。
    """
    headers = dict(response.headers)
    content_length = headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.RESPONSE_ENVELOPE_MAX_BYTES:
        return response

    raw_body = b""
    async for chunk in response.body_iterator:
        raw_body += chunk
        if len(raw_body) > settings.RESPONSE_ENVELOPE_MAX_BYTES:
            return Response(
                content=raw_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

    status_code = response.status_code
    fallback = {
        "code": status_to_error_code(status_code),
        "message": f"请求失败（HTTP {status_code}）",
        "data": None,
    }
    payload = None
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
    if payload is None and raw_body:
        # 非 JSON：原文截断入 message，保证排查线索不丢
        fallback["message"] = raw_body.decode("utf-8", errors="replace").strip()[:300] or fallback["message"]
    elif isinstance(payload, dict):
        if is_enveloped(payload) and payload.get("code") != 1000:
            return JSONResponse(status_code=status_code, content=payload, headers=headers)
        detail = payload.get("detail", payload if not is_enveloped(payload) else None)
        if detail is not None:
            fallback["message"] = str(detail)

    headers.pop("content-length", None)
    headers.pop("content-type", None)
    return JSONResponse(status_code=status_code, content=fallback, headers=headers)


def _normalize_payload(payload):
    if isinstance(payload, dict) and {"items", "total", "page", "page_size"}.issubset(payload.keys()):
        return {
            "list": payload["items"],
            "pagination": {
                "page": payload["page"],
                "size": payload["page_size"],
                "total": payload["total"],
            },
        }
    return payload
