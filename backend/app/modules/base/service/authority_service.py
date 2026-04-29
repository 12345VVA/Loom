"""
Base 模块管理端鉴权服务
"""
from __future__ import annotations

from fnmatch import fnmatch
import hashlib
from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decode_token, is_token_blacklisted
from app.framework.router.route_meta import TagTypes, get_permission_meta
from app.modules.base.compat import ADMIN_PATH_ALIASES, DEFAULT_AUTHENTICATED_PERMISSIONS, DEFAULT_PUBLIC_PERMISSION_PATHS
from app.modules.base.model.auth import Menu, Role, RoleMenuLink, User, UserRoleLink
from app.modules.base.service.cache_service import cache_delete, cache_get, cache_get_json, cache_set, cache_set_json
from app.modules.loader import load_permission_configs

ADMIN_PREFIX = "/admin"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def build_token_cache_key(user_id: int) -> str:
    return f"admin:token:{user_id}"


def build_permissions_cache_key(user_id: int) -> str:
    return f"admin:perms:{user_id}"


def build_permission_patterns_cache_key(user_id: int) -> str:
    return f"admin:permPatterns:{user_id}"


def build_permission_paths_cache_key(user_id: int) -> str:
    return f"admin:perms:path:{user_id}"


def build_password_version_cache_key(user_id: int) -> str:
    return f"admin:passwordVersion:{user_id}"


def build_token_version_cache_key(user_id: int) -> str:
    """构建用户Token版本号缓存键"""
    return f"admin:tokenVersion:{user_id}"


def build_session_tokens_cache_key(user_id: int) -> str:
    return f"admin:sessions:{user_id}"


def get_user_token_version(user_id: int) -> int:
    """获取用户当前Token版本号"""
    from app.modules.base.service.cache_service import cache_get
    version = cache_get(build_token_version_cache_key(user_id))
    return int(version) if version else 0


def increment_user_token_version(user_id: int) -> int:
    """
    递增用户Token版本号，使所有旧Token失效

    Returns:
        新的Token版本号
    """
    from app.modules.base.service.cache_service import cache_get, cache_set
    import redis

    cache_key = build_token_version_cache_key(user_id)
    current = cache_get(cache_key)

    # 使用Redis原子递增操作
    from app.core.redis import redis_client
    try:
        new_version = redis_client.incr(cache_key)
        # 设置TTL为较长的时间（如30天），避免版本号过早过期
        redis_client.expire(cache_key, 30 * 24 * 60 * 60)
    except Exception:
        # Redis不可用时回退到普通方式
        new_version = (int(current) if current else 0) + 1
        cache_set(cache_key, str(new_version), 30 * 24 * 60 * 60)

    return new_version


def build_department_cache_key(user_id: int) -> str:
    return f"admin:department:{user_id}"


def get_access_token_ttl() -> int:
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def get_refresh_token_ttl() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def get_user_roles(session: Session, user_id: int) -> list[Role]:
    statement = (
        select(Role)
        .join(UserRoleLink, UserRoleLink.role_id == Role.id)
        .where(UserRoleLink.user_id == user_id, Role.is_active == True)  # noqa: E712
    )
    return list(session.exec(statement).all())


def is_super_admin(session: Session, user: User) -> bool:
    if user.is_super_admin:
        return True
    roles = get_user_roles(session, user.id)
    return any(role.code == "admin" for role in roles)


def get_user_permissions(session: Session, user_id: int) -> list[str]:
    user = session.get(User, user_id)
    if not user:
        return []

    if is_super_admin(session, user):
        statement = select(Menu.permission).where(Menu.permission.is_not(None), Menu.is_active == True)  # noqa: E712
        return sorted({permission for permission in session.exec(statement).all() if permission} | set(DEFAULT_AUTHENTICATED_PERMISSIONS))

    role_ids = [role.id for role in get_user_roles(session, user_id) if role.id is not None]
    if not role_ids:
        return []

    statement = (
        select(Menu.permission)
        .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
        .where(RoleMenuLink.role_id.in_(role_ids), Menu.permission.is_not(None), Menu.is_active == True)  # noqa: E712
    )
    return sorted({permission for permission in session.exec(statement).all() if permission} | set(DEFAULT_AUTHENTICATED_PERMISSIONS))


def get_permission_pattern_map() -> dict[str, tuple[str, ...]]:
    return {
        permission.permission: permission.admin_patterns
        for permission in load_permission_configs()
        if permission.admin_patterns
    }


def permission_to_path(permission: str) -> str:
    return permission.replace(":", "/")


def get_permission_url_patterns(permission: str) -> list[str]:
    return list(get_permission_pattern_map().get(permission, ()))


def get_user_permission_patterns(session: Session, user: User) -> list[str]:
    cache_key = build_permission_patterns_cache_key(user.id)
    cached = cache_get_json(cache_key)
    if cached:
        return list(cached)

    if is_super_admin(session, user):
        patterns = ["*"]
    else:
        patterns_set: set[str] = set()
        for permission in DEFAULT_AUTHENTICATED_PERMISSIONS:
            patterns_set.update(get_permission_url_patterns(permission))
        for permission in get_user_permissions(session, user.id):
            patterns_set.update(get_permission_url_patterns(permission))
        patterns = sorted(patterns_set)

    cache_set_json(cache_key, patterns, get_access_token_ttl())
    return patterns


def get_user_permission_paths(session: Session, user: User) -> list[str]:
    cache_key = build_permission_paths_cache_key(user.id)
    cached = cache_get_json(cache_key)
    if cached:
        return list(cached)

    if is_super_admin(session, user):
        paths = ["*"]
    else:
        permissions = get_user_permissions(session, user.id)
        paths = sorted({permission_to_path(permission) for permission in permissions} | set(DEFAULT_PUBLIC_PERMISSION_PATHS))

    cache_set_json(cache_key, paths, get_access_token_ttl())
    return paths


def prime_login_caches(session: Session, user: User, access_token: str) -> list[str]:
    permissions = get_user_permissions(session, user.id)
    if is_super_admin(session, user):
        patterns = ["*"]
    else:
        patterns_set = {
            pattern
            for permission in (*DEFAULT_AUTHENTICATED_PERMISSIONS, *permissions)
            for pattern in get_permission_url_patterns(permission)
        }
        patterns = sorted(patterns_set)
    cache_set(build_token_cache_key(user.id), access_token, get_access_token_ttl())
    cache_set(build_password_version_cache_key(user.id), str(user.password_version), get_refresh_token_ttl())
    cache_set_json(build_permissions_cache_key(user.id), permissions, get_access_token_ttl())
    cache_set_json(build_permission_patterns_cache_key(user.id), patterns, get_access_token_ttl())
    cache_set_json(
        build_permission_paths_cache_key(user.id),
        ["*"] if is_super_admin(session, user) else sorted({permission_to_path(permission) for permission in permissions} | set(DEFAULT_PUBLIC_PERMISSION_PATHS)),
        get_access_token_ttl(),
    )
    if user.department_id is not None:
        cache_set(build_department_cache_key(user.id), str(user.department_id), get_refresh_token_ttl())
    register_user_session(user.id, access_token)
    return permissions


def build_refresh_token_cache_key(user_id: int) -> str:
    return f"admin:token:refresh:{user_id}"


def clear_login_caches(user_id: int) -> None:
    cache_delete(
        build_token_cache_key(user_id),
        build_refresh_token_cache_key(user_id),
        build_permissions_cache_key(user_id),
        build_permission_patterns_cache_key(user_id),
        build_permission_paths_cache_key(user_id),
        build_password_version_cache_key(user_id),
        build_department_cache_key(user_id),
        build_session_tokens_cache_key(user_id),
    )


def clear_login_caches_for_users(user_ids: list[int] | set[int] | tuple[int, ...]) -> None:
    for user_id in {int(item) for item in user_ids if item is not None}:
        clear_login_caches(user_id)


def clear_login_caches_for_roles(session: Session, role_ids: list[int] | set[int] | tuple[int, ...]) -> None:
    normalized = [int(item) for item in role_ids if item is not None]
    if not normalized:
        return
    user_ids = [
        item.user_id
        for item in session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(normalized))).all()
    ]
    clear_login_caches_for_users(user_ids)


def clear_login_caches_for_menus(session: Session, menu_ids: list[int] | set[int] | tuple[int, ...]) -> None:
    normalized = [int(item) for item in menu_ids if item is not None]
    if not normalized:
        return
    role_ids = [
        item.role_id
        for item in session.exec(select(RoleMenuLink).where(RoleMenuLink.menu_id.in_(normalized))).all()
    ]
    clear_login_caches_for_roles(session, role_ids)


def extract_token(request: Request) -> str:
    """提取访问令牌，支持多种标准格式"""
    authorization = request.headers.get("Authorization", "")
    if authorization:
        # 兼容 Bearer <token> 和 直接 <token>
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return authorization.strip()

    # 兼容特定前端使用的 token/x-token 请求头
    token = request.headers.get("token") or request.headers.get("x-token")
    if token:
        return token.strip()

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证信息")


def get_user_from_access_token(session: Session, token: str) -> tuple[User, dict[str, Any]]:
    payload = decode_token(token)
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌类型错误")

    # 检查Token是否在黑名单中（主动吊销）
    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌缺少用户标识")

    user = session.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    password_version = payload.get("password_version")
    token_version = payload.get("token_version") or 0

    # 强制校验数据库真实的密码版本号（最高权重，一旦密码修改，旧 Token 必须立刻失效）
    if user.password_version != password_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，密码已修改")

    # 校验Token版本号，用于强制吊销用户所有Token
    current_token_version = get_user_token_version(user.id)
    if token_version < current_token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")

    if not is_user_session_allowed(user.id, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号会话数量超过限制，请重新登录")

    cached_password_version = cache_get(build_password_version_cache_key(user.id))
    if cached_password_version is not None and str(password_version) != cached_password_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")

    cached_token = cache_get(build_token_cache_key(user.id))
    if cached_token is not None and settings.ADMIN_SSO_ENABLED and cached_token != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已在其他位置登录")

    # 如果缓存为空（例如服务端使用了内存缓存并发生重启），但 Token 的签名合法且密码版本匹对，
    # 此时静默地重新注入登录缓存，以实现服务端无缝重启用户无感
    if cached_password_version is None or cached_token is None:
        prime_login_caches(session, user, token)

    return user, payload


def register_user_session(user_id: int, token: str) -> None:
    max_sessions = settings.ADMIN_SESSION_MAX_CONCURRENT
    if max_sessions <= 0:
        return
    cache_key = build_session_tokens_cache_key(user_id)
    sessions = [item for item in (cache_get_json(cache_key) or []) if isinstance(item, str)]
    fingerprint = _token_fingerprint(token)
    sessions = [item for item in sessions if item != fingerprint]
    sessions.append(fingerprint)
    sessions = sessions[-max_sessions:]
    cache_set_json(cache_key, sessions, get_refresh_token_ttl())


def is_user_session_allowed(user_id: int, token: str) -> bool:
    max_sessions = settings.ADMIN_SESSION_MAX_CONCURRENT
    if max_sessions <= 0:
        return True
    sessions = cache_get_json(build_session_tokens_cache_key(user_id))
    if not sessions:
        return True
    return _token_fingerprint(token) in set(sessions)


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_cached_user_permissions(session: Session, user: User) -> list[str]:
    cache_key = build_permissions_cache_key(user.id)
    cached = cache_get_json(cache_key)
    if cached:
        return list(cached)
    permissions = get_user_permissions(session, user.id)
    cache_set_json(cache_key, permissions, get_access_token_ttl())
    return permissions


def authorize_admin_request(session: Session, request: Request, anonymous_paths: set[str], required_permission: str | None = None) -> User:
    request_path = request.url.path.rstrip("/") or "/"
    if request_path in anonymous_paths:
        return _cache_anonymous_user(request)

    token = extract_token(request)
    user, _ = get_user_from_access_token(session, token)

    request.state.current_user = user
    request.state.permissions = get_cached_user_permissions(session, user)
    request.state.permission_patterns = get_user_permission_patterns(session, user)
    request.state.permission_paths = get_user_permission_paths(session, user)

    if is_super_admin(session, user):
        return user

    if required_permission:
        if has_permission(request.state.permissions, required_permission):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问当前接口")

    normalized_request_path = canonicalize_admin_path(request_path)

    if has_admin_path_permission(request.state.permission_paths, normalized_request_path):
        return user

    if not has_url_permission(request.state.permission_patterns, request.method, normalized_request_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问当前接口")

    return user


def authenticate_scoped_request(session: Session, request: Request) -> User:
    token = extract_token(request)
    user, _ = get_user_from_access_token(session, token)
    request.state.current_user = user
    return user


def authorize_request(
    session: Session,
    request: Request,
    scope_name: str,
    route_tags: set[str],
    scope_whitelist: set[str],
    matched_route=None,
) -> User | None:
    request_path = request.url.path.rstrip("/") or "/"
    ignore_token = TagTypes.IGNORE_TOKEN in route_tags or request_path in scope_whitelist
    if ignore_token:
        return _cache_anonymous_user(request)

    if scope_name == "admin":
        ignore_permission = TagTypes.IGNORE_PERMISSION in route_tags
        if ignore_permission:
            return authenticate_scoped_request(session, request)
        required_permission = get_permission_meta(matched_route.endpoint) if matched_route else None
        return authorize_admin_request(session, request, scope_whitelist, required_permission=required_permission)

    return authenticate_scoped_request(session, request)


def has_url_permission(patterns: list[str], method: str, request_path: str) -> bool:
    if "*" in patterns:
        return True

    normalized_path = request_path.rstrip("/") or "/"
    for pattern in patterns:
        method_name, _, raw_path_pattern = pattern.partition(" ")
        path_pattern = raw_path_pattern or method_name
        expected_method = method_name if raw_path_pattern else None
        if expected_method and expected_method.upper() != method.upper():
            continue
        if fnmatch(normalized_path, path_pattern.rstrip("/") or "/"):
            return True
    return False


def has_permission(permissions: list[str], required_permission: str) -> bool:
    return required_permission in permissions or "*" in permissions


def has_admin_path_permission(permission_paths: list[str], request_path: str) -> bool:
    if "*" in permission_paths:
        return True
    normalized_path = request_path.rstrip("/") or "/"
    if not normalized_path.startswith(f"{ADMIN_PREFIX}/"):
        return False
    resource_path = normalized_path.removeprefix(f"{ADMIN_PREFIX}/")
    if resource_path in permission_paths:
        return True
    return any(fnmatch(resource_path, f"{path}*") for path in permission_paths)


def canonicalize_admin_path(request_path: str) -> str:
    normalized = request_path.rstrip("/") or "/"
    for alias, target in ADMIN_PATH_ALIASES.items():
        if normalized == alias or normalized.startswith(f"{alias}/"):
            suffix = normalized.removeprefix(alias)
            return f"{target}{suffix}".rstrip("/") or "/"
    return normalized


def _cache_anonymous_user(request: Request) -> User:
    anonymous = getattr(request.state, "current_user", None)
    if anonymous is None:
        anonymous = User(id=0, username="anonymous", full_name="anonymous", password_hash="", is_active=True)
        request.state.current_user = anonymous
    return anonymous
