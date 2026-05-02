"""
敏感配置加密工具。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.core.config import settings


_VERSION = "v1"


def encrypt_secret(value: str | None) -> str | None:
    """使用 SECRET_ENCRYPTION_KEY 加密敏感值。"""
    if not value:
        return None
    key = _derive_key()
    nonce = os.urandom(16)
    plain = value.encode("utf-8")
    cipher = _xor_bytes(plain, _keystream(key, nonce, len(plain)))
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    payload = base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")
    return f"{_VERSION}:{payload}"


def decrypt_secret(value: str | None) -> str | None:
    """解密 encrypt_secret 生成的密文。"""
    if not value:
        return None
    if not value.startswith(f"{_VERSION}:"):
        return value
    key = _derive_key()
    raw = base64.urlsafe_b64decode(value.split(":", 1)[1].encode("ascii"))
    nonce, mac, cipher = raw[:16], raw[16:48], raw[48:]
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("密钥密文校验失败")
    plain = _xor_bytes(cipher, _keystream(key, nonce, len(cipher)))
    return plain.decode("utf-8")


def mask_secret(value: str | None) -> str | None:
    """生成适合列表/详情展示的密钥掩码。"""
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _derive_key() -> bytes:
    raw = settings.SECRET_ENCRYPTION_KEY or settings.JWT_SECRET_KEY
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < size:
        counter_bytes = counter.to_bytes(8, "big")
        blocks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:size]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))
