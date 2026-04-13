"""
基础安全工具
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import settings


def hash_password(password: str) -> str:
    """使用 PBKDF2 生成密码哈希"""
    iterations = 100_000
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.b64encode(salt).decode()}$"
        f"{base64.b64encode(derived).decode()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码"""
    try:
        _, iteration_text, salt_text, hash_text = password_hash.split("$", 3)
        iterations = int(iteration_text)
        salt = base64.b64decode(salt_text.encode())
        expected_hash = base64.b64decode(hash_text.encode())
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected_hash)


def create_token(payload: dict[str, Any], expires_delta: timedelta) -> str:
    """生成 JWT"""
    expire_at = datetime.now(timezone.utc) + expires_delta
    token_payload = {**payload, "exp": expire_at, "iat": datetime.now(timezone.utc)}
    return jwt.encode(token_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT"""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效或已过期",
        ) from exc
