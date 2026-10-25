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
