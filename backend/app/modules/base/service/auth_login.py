"""登录/刷新令牌/风控计数域（AuthService 的 login 分域 mixin）。"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlmodel import select

from app.core.config import settings
from app.core.security import (
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.modules.base.model.auth import (
    CoolLoginResponse,
    LoginRequest,
    RefreshTokenRequest,
    Role,
    User,
)
from app.modules.base.service.auth_request_info import (
    _get_client_type,
    _get_device_id,
    _get_request_ip,
    _get_user_agent,
)
from app.modules.base.service.authority_service import (
    delete_session,
    get_session,
    get_user_token_version,
    increment_user_token_version,
    prime_login_caches,
    refresh_session,
    register_session,
)
from app.modules.base.service.cache_service import cache_delete, cache_get, cache_incr, cache_set
from app.modules.base.service.security_service import (
    create_access_token,
    create_refresh_token,
    get_refresh_token_payload,
    get_user_roles,
)
from app.modules.base.service.sys_manage_service import SysLoginLogService

# 登录时序侧信道防护：用户不存在时也用此 dummy 哈希跑一次等价耗时的 PBKDF2，
# 使"用户不存在"与"密码错误"的响应时间一致，防止攻击者据此枚举有效账号。
_DUMMY_PASSWORD_HASH = hash_password("__invalid_dummy_account__")

logger = logging.getLogger(__name__)


class LoginMixin:
    """登录、令牌刷新与登录风控。依赖宿主提供 `self.session`。"""

    def login(self, payload: LoginRequest, request: Request | None = None) -> CoolLoginResponse:
        login_ip = _get_request_ip(request) or "unknown"
        locked_reason = self._check_login_risk(payload.username, login_ip)
        if locked_reason:
            self._record_login_log(
                request=request,
                account=payload.username,
                status=0,
                reason=locked_reason,
                risk_hit=1,
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=locked_reason)

        if settings.captcha_enabled:
            try:
                # L3：校验与签发的 IP 绑定一致性
                self.captcha_check(payload.captcha_id, payload.verify_code, client_ip=login_ip)
            except HTTPException as exc:
                # H2：验证码失败只计 IP 失败计数，不计账号——校验无需凭证，
                # 计入账号即成"仅凭用户名锁死任意账号"的 DoS 原语
                self._mark_login_failure(payload.username, login_ip, count_account=False)
                self._record_login_log(
                    request=request,
                    account=payload.username,
                    status=0,
                    reason=exc.detail if isinstance(exc.detail, str) else "验证码不正确",
                    risk_hit=1,
                )
                raise

        statement = select(User).where(User.username == payload.username)
        user = self.session.exec(statement).first()

        # 时序一致性：用户不存在时也用 dummy 哈希跑一次 PBKDF2，
        # 避免"用户不存在"响应快于"密码错误"而泄露账号存在性
        password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(payload.password, password_hash)

        if not user or not password_ok:
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name if user else None,
                user_id=user.id if user else None,
                status=0,
                reason="用户名或密码错误",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
            self.session.add(user)

        # 账号状态异常：对外统一为"用户名或密码错误"以避免泄露账号存在性与状态，
        # 真实原因仅写入登录日志供管理员排查
        if not user.is_active:
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name,
                user_id=user.id,
                status=0,
                reason="用户已禁用",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        roles = get_user_roles(self.session, user.id)
        if not roles:
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name,
                user_id=user.id,
                status=0,
                reason="当前用户未分配角色",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        user._token_role_ids = [role.id for role in roles if role.id is not None]

        user.last_login_at = datetime.now(UTC)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

        # 检查是否需要强制修改密码（从未修改过密码或密码是默认值）
        force_password_change = False
        if user.password_changed_at is None:
            # 首次登录或从未修改过密码
            force_password_change = True

        # 多设备会话：每次登录生成独立 sid，签发带 sid 的 token 并注册会话记录（含设备/IP）
        sid = uuid4().hex
        access_token = create_access_token(user, sid)
        refresh_token = create_refresh_token(user, sid)
        permissions = prime_login_caches(self.session, user, access_token)
        register_session(user.id, sid, refresh_token, decode_token(access_token).get("jti"), request)
        self._clear_login_failure(payload.username)
        self._record_login_log(
            request=request,
            user_id=user.id,
            name=user.full_name,
            account=user.username,
            status=1,
        )
        return self._finalize_login_response(
            user=user,
            roles=roles,
            permissions=permissions,
            access_token=access_token,
            refresh_token=refresh_token,
            force_password_change=force_password_change,
        )

    def _finalize_login_response(
        self,
        *,
        user: User,
        roles: list[Role],
        permissions: list[str],
        access_token: str,
        refresh_token: str,
        force_password_change: bool = False,
    ) -> CoolLoginResponse:
        response = CoolLoginResponse(
            token=access_token,
            refresh_token=refresh_token,
            expire=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_expire=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            user_info=self.build_user_info(
                user, roles=roles, permissions=permissions, force_password_change=force_password_change
            ),
            permission=permissions,
        )
        return response

    def refresh_token(self, payload: RefreshTokenRequest) -> CoolLoginResponse:
        return self.refresh_token_by_value(payload.token_value)

    def refresh_token_by_value(self, refresh_token_value: str | None) -> CoolLoginResponse:
        """
        根据 refresh_token 字符串换发新的访问令牌。

        支持从 HttpOnly cookie 或请求 body 传入 refresh_token：
        - 主路径：HttpOnly cookie（前端不再存储 refreshToken）
        - 兼容路径：请求 body（旧客户端/测试用例）
        """
        if not refresh_token_value:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌不能为空")
        token_payload = get_refresh_token_payload(refresh_token_value)
        user_id = token_payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌缺少用户标识")

        user = self.session.get(User, int(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

        token_password_version = token_payload.get("password_version")
        if user.password_version != token_password_version:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效")

        # token_version 校验：覆盖强制踢出/改密码场景（increment_user_token_version 后旧 token 失效）。
        # 与 password_version 互补：password_version 仅在改密码时递增，token_version 在全设备登出时递增。
        token_version = int(token_payload.get("token_version") or 0)
        if token_version < get_user_token_version(user.id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")

        # 会话校验：refresh_token 须对应一个仍存活的本设备会话（logout/被踢/被挤掉后删除即拒）。
        # 多设备各自独立会话、互不覆盖——这是多设备并行登录的关键。
        sid = token_payload.get("sid")
        if not sid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")
        session_record = get_session(user.id, sid)
        if not session_record:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")
        # 恒定时间比较 refresh_hash，防止按字节前缀差异的定时侧信道泄露 refresh_token
        provided_hash = hashlib.sha256(refresh_token_value.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(str(session_record.get("refresh_hash")), provided_hash):
            # R7：提交「上一代已轮转」的 refresh token = 令牌家族泄露信号（合法客户端
            # 只持最新代）——整族作废并删除会话，防窃取者与合法用户并存续期；
            # 合法用户下一次刷新将失败并需重新登录（可感知告警，而非被静默顶替）
            self._revoke_stolen_session_family(user, session_record, provided_hash)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")

        roles = get_user_roles(self.session, user.id)
        user._token_role_ids = [role.id for role in roles if role.id is not None]
        access_token = create_access_token(user, sid)
        refresh_token = create_refresh_token(user, sid)
        permissions = prime_login_caches(self.session, user, access_token)
        refresh_session(user.id, sid, refresh_token, decode_token(access_token).get("jti"))
        return self._finalize_login_response(
            user=user,
            roles=roles,
            permissions=permissions,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def _revoke_stolen_session_family(self, user: User, session_record: dict, provided_hash: str) -> None:
        """R7：refresh 重用检测——提交的 hash 匹配「上一代」refresh hash 时，
        判定令牌家族已泄露：递增 token_version 作废该用户全部令牌并删除会话，
        写告警日志供审计。非重用（纯无效 token）不做任何动作，由调用方统一 401。"""
        prev_hash = str(session_record.get("prev_refresh_hash") or "")
        if not prev_hash or not hmac.compare_digest(prev_hash, provided_hash):
            return
        sid = str(session_record.get("sid") or "")
        increment_user_token_version(user.id)
        if sid:
            delete_session(user.id, sid)
        logger.warning(
            "检测到 refresh token 重用（令牌家族泄露信号，R7）：user_id=%s sid=%s 已整族作废并删除会话",
            user.id,
            sid,
        )

    def _record_login_log(
        self,
        *,
        request: Request | None,
        account: str | None,
        status: int,
        reason: str | None = None,
        user_id: int | None = None,
        name: str | None = None,
        login_type: str = "password",
        risk_hit: int = 0,
    ) -> None:
        try:
            SysLoginLogService(self.session).create_entry(
                user_id=user_id,
                name=name,
                account=account,
                login_type=login_type,
                status=status,
                ip=_get_request_ip(request),
                reason=reason,
                risk_hit=risk_hit,
                user_agent=_get_user_agent(request),
                client_type=_get_client_type(request),
                device_id=_get_device_id(request),
                source_system="管理后台",
            )
        except Exception as exc:
            # 日志写入失败应记录错误日志，便于排查问题
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"登录日志写入失败 - account: {account}, user_id: {user_id}, status: {status}", exc_info=exc)

    def _check_login_risk(self, account: str, ip: str) -> str | None:
        if cache_get(self._build_account_lock_key(account)):
            return "账号已被临时锁定，请稍后再试"
        if cache_get(self._build_ip_lock_key(ip)):
            return "当前IP请求过于频繁，请稍后再试"
        return None

    def _mark_login_failure(self, account: str, ip: str, *, count_account: bool = True) -> int:
        """累计登录失败（账号+IP 双计数）并在达阈值时锁定。

        count_account=False：仅计 IP 计数——用于验证码失败分支（H2）。验证码校验发生在
        密码校验之前且无需任何凭证，若计入账号计数，仅凭用户名 5 次请求即可锁死任意
        账号 15 分钟（DoS 原语）。IP 计数保留：同一 IP 持续撞验证码仍受 20 次/15min 锁约束。
        """
        account_failures = (
            self._increase_counter(self._build_account_fail_key(account), settings.BASE_LOGIN_FAIL_WINDOW)
            if count_account
            else 0
        )
        ip_failures = self._increase_counter(self._build_ip_fail_key(ip), settings.BASE_LOGIN_FAIL_WINDOW)
        risk_hit = 0
        if account_failures >= settings.BASE_LOGIN_ACCOUNT_FAIL_MAX:
            cache_set(self._build_account_lock_key(account), "1", settings.BASE_LOGIN_LOCK_TIME)
            risk_hit = 1
        if ip_failures >= settings.BASE_LOGIN_IP_FAIL_MAX:
            cache_set(self._build_ip_lock_key(ip), "1", settings.BASE_LOGIN_LOCK_TIME)
            risk_hit = 1
        return risk_hit

    def _clear_login_failure(self, account: str) -> None:
        """成功登录只清账号维度计数/锁（R3）。

        此前连 `login:fail:ip` / `login:lock:ip` 一起删——持有任意有效低权账号即可在
        爆破轮次间登录一次，把整台 IP 的失败计数与锁清零，用户名喷洒自此仅受
        /login 限流约束。IP 维度自清靠 TTL（BASE_LOGIN_FAIL_WINDOW）滚动到期。
        IP 锁存在时登录在 `_check_login_risk` 即被 429，成功登录本就不可达，
        「清 IP 锁」对锁场景原是死路径；保留 IP 计数对共享出口 IP 的额外代价
        由 20 次/15min 的高阈值与 15min 窗口兜底。
        """
        cache_delete(
            self._build_account_fail_key(account),
            self._build_account_lock_key(account),
        )

    @staticmethod
    def _increase_counter(key: str, ttl_seconds: int) -> int:
        # 原子递增（Redis pipeline INCR+EXPIRE），避免并发 read-modify-write 丢失更新
        # 导致锁定阈值被绕过。Redis 异常时返回 None（已降级内存计数），fail-open 不误锁。
        value = cache_incr(key, ttl_seconds)
        return value if value is not None else 0

    @staticmethod
    def _build_account_fail_key(account: str) -> str:
        return f"login:fail:account:{account}"

    @staticmethod
    def _build_ip_fail_key(ip: str) -> str:
        return f"login:fail:ip:{ip}"

    @staticmethod
    def _build_account_lock_key(account: str) -> str:
        return f"login:lock:account:{account}"

    @staticmethod
    def _build_ip_lock_key(ip: str) -> str:
        return f"login:lock:ip:{ip}"
