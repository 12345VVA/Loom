"""
Base 模块认证依赖服务
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_token, decode_token
from app.modules.base.model.auth import User
from app.modules.base.service.authority_service import (
    get_user_from_access_token,
    get_user_permissions,
    get_user_roles,
    has_url_permission,
)

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    role_codes = get_user_roles_cached(user)
    return create_token(
        {
            "sub": str(user.id),
            "type": "access",
            "userId": user.id,
            "username": user.username,
            "roleIds": role_codes["role_ids"],
            "password_version": user.password_version,
            "passwordVersion": user.password_version,
            "isRefresh": False,
            "jti": uuid4().hex,
        },
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user: User) -> str:
    role_codes = get_user_roles_cached(user)
    return create_token(
        {
            "sub": str(user.id),
            "type": "refresh",
            "userId": user.id,
            "username": user.username,
            "roleIds": role_codes["role_ids"],
            "password_version": user.password_version,
            "passwordVersion": user.password_version,
            "isRefresh": True,
            "jti": uuid4().hex,
        },
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None and getattr(cached_user, "id", None) not in (None, 0):
        return cached_user

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证信息")

    user, _ = get_user_from_access_token(session, credentials.credentials)
    request.state.current_user = user
    return user


def get_refresh_token_payload(refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    is_refresh = payload.get("type") == "refresh" or bool(payload.get("isRefresh"))
    if not is_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
    return payload


def ensure_permission_patterns(request: Request, method: str, path: str) -> None:
    patterns = getattr(request.state, "permission_patterns", None) or []
    if not has_url_permission(patterns, method, path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问当前接口")


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "ensure_permission_patterns",
    "get_current_user",
    "get_refresh_token_payload",
    "get_user_permissions",
    "get_user_roles",
]


def get_user_roles_cached(user: User) -> dict[str, list[int]]:
    role_ids = getattr(user, "_token_role_ids", None)
    if role_ids is None:
        role_ids = []
    return {"role_ids": role_ids}
