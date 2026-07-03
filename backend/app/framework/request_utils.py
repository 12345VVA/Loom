"""
请求工具函数

集中放置与 HTTP Request 相关的共享解析逻辑，避免在多个模块中重复实现。
"""

from __future__ import annotations

from starlette.requests import Request

from app.core.config import settings


def get_client_ip(request: Request) -> str:
    """
    解析真实客户端 IP。

    安全策略：
    - 仅当配置了 TRUSTED_PROXIES 时才信任 X-Forwarded-For；
      否则直接使用 socket 对端 IP，防止伪造 X-Forwarded-For 绕过限流/登录失败锁定。
    - 配置可信代理后，从右向左跳过可信代理 IP，取第一个非可信 IP 作为真实客户端。
    - 不读取 X-Real-IP：该头同样可被客户端伪造，socket 对端 IP 已是最可靠回退。
    - 兜底返回 "unknown"（socket 不可用且 X-Forwarded-For 未命中场景）。

    调用方若需要区分"未知 IP"与"有效 IP"（例如登录日志中用 None 表示未知），
    可在外层将 "unknown" 转换为期望的哨兵值。
    """
    # trusted 为空（默认）时跳过 X-Forwarded-For 全部逻辑，回退 socket 对端 IP——有意设计
    trusted = settings.trusted_proxies_list
    forwarded = request.headers.get("x-forwarded-for")
    # 仅当直连对端本身是可信代理时才信任 X-Forwarded-For；
    # 否则攻击者可绕过反代直连后端伪造 XFF，绕过限流/登录失败锁定
    peer = request.client.host if request.client else None
    if forwarded and trusted and peer in trusted:
        proxies = [item.strip() for item in forwarded.split(",") if item.strip()]
        for ip in reversed(proxies):
            if ip not in trusted:
                return ip
        # 全部都是可信代理：回退到 socket 对端 IP
    if request.client:
        return request.client.host
    return "unknown"
