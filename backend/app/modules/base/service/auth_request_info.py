"""认证域共用的请求信息解析工具（从 auth_service 拆出，login/session 两域共用）。"""

from __future__ import annotations

import hashlib

from fastapi import Request

from app.framework.request_utils import get_client_ip


def _get_request_ip(request: Request | None) -> str | None:
    """
    解析真实客户端 IP。

    薄包装：委托给共享实现 `app.framework.request_utils.get_client_ip`，
    保留原 `_get_request_ip` 的 None 语义（request 为 None 或 socket 不可用时返回 None，
    用于登录日志场景，未知 IP 用 None 表示更合适）。

    安全策略见 `get_client_ip` 文档。
    """
    if request is None:
        return None
    ip = get_client_ip(request)
    # get_client_ip 在 X-Forwarded-For 未命中且 socket 不可用时返回 "unknown"，
    # 等价于原 _get_request_ip 在 request.client 为 None 时的 None 兜底。
    return None if ip == "unknown" else ip


def _get_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")


def _get_client_type(request: Request | None) -> str | None:
    user_agent = (_get_user_agent(request) or "").lower()
    if not user_agent:
        return None
    if "mobile" in user_agent or "android" in user_agent or "iphone" in user_agent or "ipad" in user_agent:
        return "移动端"
    return "PC"


def _get_device_id(request: Request | None) -> str | None:
    if request is None:
        return None
    explicit = request.headers.get("x-device-id") or request.headers.get("device-id")
    if explicit:
        return explicit
    source = "|".join(
        [
            _get_request_ip(request) or "",
            _get_user_agent(request) or "",
            request.headers.get("accept-language", ""),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24] if source.strip("|") else None
