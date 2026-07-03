"""SSRF 防护工具：校验远程 URL 安全性并返回 IP 直连 URL 以缓解 DNS rebinding TOCTOU。

供媒体转存、AI 适配器下载远程资源等场景复用。
"""

from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

import httpx

from app.core.config import settings

# 代理/基准测试网段（部分云厂商内部使用），未列入白名单时视为内网
_PROXY_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def validate_remote_url(url: str) -> tuple[str, str]:
    """校验远程 URL 安全性，返回 (替换为 IP 的 URL, 原 hostname)。

    为避免 DNS rebinding TOCTOU：校验解析的 IP 后，将 URL 中 hostname 替换为已校验的 IP，
    调用方据此 URL 直接发起请求并附 ``Host`` header 指向原 hostname，httpx 不再重新解析 DNS。

    安全策略：
    - 仅允许 http/https 协议
    - 拒绝 localhost / 回环 / 私有 / 链路本地 / 元数据服务 / 非全球单播地址
    - 对域名做 DNS 解析后逐个校验解析结果 IP
    - 代理网段 (198.18.0.0/15) 仅在白名单内放行

    Raises:
        ValueError: URL 不合法或解析到内网地址。
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持 http/https 媒体 URL")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("不允许访问本地地址")

    hostname = parsed.hostname.lower().rstrip(".")
    is_allowed_host = _is_allowed_remote_host(hostname)
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("远程 URL 域名解析失败") from exc
    resolved_ip: str | None = None
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip in _PROXY_NETWORK:
            if not is_allowed_host:
                # 未列入白名单的代理网段地址视为内网，避免 SSRF
                raise ValueError("不允许访问内网地址")
            if resolved_ip is None:
                resolved_ip = str(ip)
            continue
        if not ip.is_global:
            raise ValueError("不允许访问内网地址")
        if resolved_ip is None:
            resolved_ip = str(ip)
    if resolved_ip is None:
        raise ValueError("远程 URL 域名未解析到有效 IP")
    # 构造替换 hostname 为已校验 IP 的新 URL，保留端口/路径/查询参数
    new_netloc = _build_ip_netloc(resolved_ip, parsed.port)
    safe_url = parsed._replace(netloc=new_netloc).geturl()
    return safe_url, hostname


def _build_ip_netloc(ip: str, port: int | None) -> str:
    """构造以 IP 为 netloc 的 URL 主机段；IPv6 用方括号包裹。"""
    is_ipv6 = ":" in ip and not ip.startswith("[")
    if is_ipv6:
        return f"[{ip}]:{port}" if port else f"[{ip}]"
    return f"{ip}:{port}" if port else ip


def _is_allowed_remote_host(hostname: str) -> bool:
    for pattern in _remote_allowed_host_patterns():
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if hostname.endswith(suffix) and hostname != suffix.lstrip("."):
                return True
            continue
        if hostname == pattern:
            return True
    return False


def _remote_allowed_host_patterns() -> list[str]:
    return [
        item.strip().lower().rstrip(".")
        for item in (settings.MEDIA_REMOTE_ALLOWED_HOSTS or "").split(",")
        if item.strip()
    ]


@contextmanager
def safe_stream(method: str, safe_url: str, hostname: str | None, **kwargs):
    """对已校验的 IP URL 发起流式请求，TLS 的 SNI/证书校验改用原 hostname。

    validate_remote_url 把 netloc 替换为已校验 IP 以缓解 DNS rebinding TOCTOU，
    但 httpx 默认以 netloc(host) 作为 SNI 与证书校验的 server_hostname，对需要 SNI 的
    CDN/HTTPS 源会握手失败或证书不匹配。此处通过 httpcore 的 extensions["sni_hostname"]
    覆盖 server_hostname：TCP 连接到已校验 IP，SNI/证书按原 hostname 校验。
    顶层 httpx.stream 不透传 extensions，故须经 Client.stream 发起请求。
    """
    kwargs.setdefault("timeout", 30)
    # 强制禁止重定向：SSRF 防护要求对重定向目标重新走 validate_remote_url 校验，
    # 跟随重定向会绕过 IP 黑名单（重定向目标可能是内网/元数据地址）。
    # 即使调用方误传 follow_redirects=True 也在此硬覆盖为 False。
    kwargs["follow_redirects"] = False
    extensions = {"sni_hostname": hostname} if hostname else None
    with httpx.Client() as client:
        with client.stream(method, safe_url, extensions=extensions, **kwargs) as response:
            yield response
