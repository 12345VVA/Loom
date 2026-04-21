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


# 常见弱密码黑名单
COMMON_WEAK_PASSWORDS = {
    "123456", "password", "12345678", "qwerty", "123456789",
    "12345", "1234", "111111", "1234567", "dragon", "123123",
    "baseball", "abc123", "football", "monkey", "letmein",
    "shadow", "master", "666666", "qwertyuiop", "123321",
    "mustang", "1234567890", "michael", "654321", "superman",
    "1qaz2wsx", "7777777", "121212", "000000", "qazwsx",
    "123qwe", "killer", "trustno1", "password1", "admin123"
}


def validate_password_strength(password: str) -> None:
    """
    验证密码强度
    要求：至少8位，包含大小写字母、数字、特殊字符中的至少3种
    不在常见弱密码黑名单中
    """
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码不能为空")

    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码长度至少8位")

    if password.lower() in COMMON_WEAK_PASSWORDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码过于简单，请使用更复杂的密码")

    # 检查字符类型
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password)

    complexity_count = sum([has_upper, has_lower, has_digit, has_special])
    if complexity_count < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码强度不足：需包含大写字母、小写字母、数字、特殊字符中的至少3种"
        )


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


# Token 黑名单相关函数

def build_token_blacklist_key(jti: str) -> str:
    """构建Token黑名单缓存键"""
    return f"token:blacklist:{jti}"


def add_token_to_blacklist(jti: str, expires_at: int) -> None:
    """
    将Token加入黑名单

    Args:
        jti: JWT ID (Token唯一标识)
        expires_at: Token过期时间戳(秒)，用于设置黑名单TTL
    """
    from app.core.redis import redis_client
    from app.modules.base.service.cache_service import get_access_token_ttl

    # 计算剩余有效时间作为TTL，最少保留60秒避免时序问题
    ttl = max(expires_at - int(datetime.now(timezone.utc).timestamp()), 60)
    redis_client.set(build_token_blacklist_key(jti), "1", ex=ttl)


def is_token_blacklisted(jti: str) -> bool:
    """检查Token是否在黑名单中"""
    from app.core.redis import redis_client

    return redis_client.exists(build_token_blacklist_key(jti)) > 0


def add_user_all_tokens_to_blacklist(user_id: int, current_token_jti: str | None = None) -> None:
    """
    将用户的所有Token加入黑名单（通过递增Token版本号实现）

    Args:
        user_id: 用户ID
        current_token_jti: 当前Token的JTI（可选，未使用，保留以兼容未来扩展）
    """
    from app.modules.base.service.authority_service import increment_user_token_version

    # 递增Token版本号，使该用户所有已签发的Token失效
    increment_user_token_version(user_id)
