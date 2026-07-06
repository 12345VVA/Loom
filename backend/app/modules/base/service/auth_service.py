"""
Base 模块认证与权限服务
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import (
    add_token_to_blacklist,
    add_user_all_tokens_to_blacklist,
    decode_token,
    hash_password,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.framework.request_utils import get_client_ip
from app.modules.base.compat import SYSTEM_MANAGED_CODE_PREFIXES
from app.modules.base.model.auth import (
    CaptchaResponse,
    CoolLoginResponse,
    CoolMenuItem,
    CoolUserInfo,
    Department,
    LoginRequest,
    Menu,
    RefreshTokenRequest,
    Role,
    RoleDepartmentLink,
    RoleMenuLink,
    User,
    UserPersonRead,
    UserPersonUpdateRequest,
    UserRoleLink,
)
from app.modules.base.service.admin_service import MenuAdminService
from app.modules.base.service.authority_service import (
    build_refresh_token_cache_key,
    clear_login_caches,
    clear_login_caches_for_users,
    get_refresh_token_ttl,
    get_user_token_version,
    prime_login_caches,
)
from app.modules.base.service.cache_service import cache_delete, cache_get, cache_get_del, cache_incr, cache_set
from app.modules.base.service.security_service import (
    create_access_token,
    create_refresh_token,
    get_refresh_token_payload,
    get_user_permissions,
    get_user_roles,
)
from app.modules.base.service.sys_manage_service import SysLoginLogService
from app.modules.loader import load_menu_manifest_items

# 登录时序侧信道防护：用户不存在时也用此 dummy 哈希跑一次等价耗时的 PBKDF2，
# 使"用户不存在"与"密码错误"的响应时间一致，防止攻击者据此枚举有效账号。
_DUMMY_PASSWORD_HASH = hash_password("__invalid_dummy_account__")

# captcha 参数校验范围
CAPTCHA_WIDTH_MIN = 80
CAPTCHA_WIDTH_MAX = 300
CAPTCHA_HEIGHT_MIN = 80
CAPTCHA_HEIGHT_MAX = 300
_CAPTCHA_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class AuthService:
    """认证服务"""

    def __init__(self, session: Session):
        self.session = session

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
                self.captcha_check(payload.captcha_id, payload.verify_code)
            except HTTPException as exc:
                self._mark_login_failure(payload.username, login_ip)
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

        user.last_login_at = datetime.now(timezone.utc)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

        # 检查是否需要强制修改密码（从未修改过密码或密码是默认值）
        force_password_change = False
        if user.password_changed_at is None:
            # 首次登录或从未修改过密码
            force_password_change = True

        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        permissions = prime_login_caches(self.session, user, access_token)
        cache_set(build_refresh_token_cache_key(user.id), refresh_token, get_refresh_token_ttl())
        self._clear_login_failure(payload.username, login_ip)
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

        # 服务端缓存校验：refresh_token 必须等于登录时缓存值
        # 防止 logout 后旧 refresh_token 仍可换新 access token
        cached_refresh_token = cache_get(build_refresh_token_cache_key(user.id))
        if cached_refresh_token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")
        # 恒定时间比较，避免按字节前缀差异的定时侧信道泄露 refresh_token
        if not hmac.compare_digest(cached_refresh_token, refresh_token_value):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效，请重新登录")

        roles = get_user_roles(self.session, user.id)
        user._token_role_ids = [role.id for role in roles if role.id is not None]
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        permissions = prime_login_caches(self.session, user, access_token)
        cache_set(build_refresh_token_cache_key(user.id), refresh_token, get_refresh_token_ttl())
        return self._finalize_login_response(
            user=user,
            roles=roles,
            permissions=permissions,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def logout(self, user: User, request: Request | None = None) -> None:
        # 将当前Token加入黑名单
        if request:
            try:
                from app.modules.base.service.authority_service import extract_token

                token = extract_token(request)
                payload = decode_token(token)
                jti = payload.get("jti")
                exp = payload.get("exp")
                if jti and exp:
                    add_token_to_blacklist(jti, exp)
            except Exception:
                # Token解析失败不影响登出流程
                pass

        # 登录日志写入失败不应阻塞登出与缓存清理（避免日志异常导致登出接口 500 失败）
        try:
            self._record_login_log(
                request=request,
                user_id=user.id,
                name=user.full_name,
                account=user.username,
                login_type="logout",
                status=1,
            )
        except Exception:
            pass
        # 递增 token_version 使该用户所有已签发 token 立即失效（踢出全部设备），
        # 避免默认 ADMIN_SESSION_MAX_CONCURRENT=0 下其他设备 access token 在自然过期前继续可用
        try:
            add_user_all_tokens_to_blacklist(user.id)
        except Exception:
            pass
        clear_login_caches(user.id)

    def revoke_by_cookie(self, request: Request) -> None:
        """best-effort 登出清理：仅凭 access token / refresh cookie 提取 user_id 清缓存。
        用于被动登出（access token 可能已失效）场景，配合 _clear_refresh_token_cookie 确保
        refresh cookie 与服务端缓存被清除，避免共享设备残留 cookie 被续期冒充。
        """
        user_id = None
        # access token 进黑名单并尝试取 user_id（token 可能已失效，全部 try 忽略）
        try:
            from app.modules.base.service.authority_service import extract_token

            token = extract_token(request)
            payload = decode_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                add_token_to_blacklist(jti, exp)
            user_id = payload.get("sub") or payload.get("userId")
        except Exception:
            pass

        # access token 失效时，从 refresh cookie 提取 user_id
        if not user_id:
            try:
                refresh_token = request.cookies.get("refresh_token")
                if refresh_token:
                    user_id = get_refresh_token_payload(refresh_token).get("sub")
            except Exception:
                pass

        if user_id:
            try:
                clear_login_caches(int(user_id))
            except Exception:
                pass

    @staticmethod
    def _random_light_color(rng) -> tuple[int, int, int]:
        """浅色随机背景色（验证码底色，配合噪声线条防 OCR 轻易定位缺口）。"""
        return (rng.randint(180, 230), rng.randint(180, 230), rng.randint(180, 230))

    @staticmethod
    def _image_to_data_url(img) -> str:
        """PIL 图像转 data URL（PNG base64）。"""
        import base64
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def _render_captcha_images(
        self, width: int, height: int, target_x: int, target_y: int, puzzle_size: int
    ):
        """生成带缺口的背景图与滑块拼图块。缺口位置即答案，但不以数值返回前端。"""
        import random

        from PIL import Image, ImageDraw

        rng = random.Random()
        # 背景：浅色 + 随机噪声线条，避免纯色下缺口过于醒目
        bg = Image.new("RGB", (width, height), self._random_light_color(rng))
        draw = ImageDraw.Draw(bg)
        for _ in range(60):
            draw.line(
                [
                    rng.randint(0, width),
                    rng.randint(0, height),
                    rng.randint(0, width),
                    rng.randint(0, height),
                ],
                fill=self._random_light_color(rng),
                width=1,
            )
        # 滑块 = 裁剪缺口位置的背景内容（真正的拼图块），用户拖它对齐缺口
        slider = bg.crop(
            (target_x, target_y, target_x + puzzle_size, target_y + puzzle_size)
        ).convert("RGBA")
        # 在背景挖缺口：半透明暗块 + 描边，提示拼合位置
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rounded_rectangle(
            [target_x, target_y, target_x + puzzle_size, target_y + puzzle_size],
            radius=8,
            fill=(0, 0, 0, 110),
            outline=(255, 255, 255, 220),
            width=2,
        )
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
        # 滑块加描边，拖动时与背景区分
        sdraw = ImageDraw.Draw(slider)
        sdraw.rounded_rectangle(
            [0, 0, puzzle_size - 1, puzzle_size - 1],
            radius=8,
            outline=(40, 40, 40, 255),
            width=2,
        )
        return bg, slider

    def captcha(self, width: int = 150, height: int = 80, color: str = "#333333") -> CaptchaResponse:
        # 参数范围校验，防止恶意输入
        try:
            width_int = int(width)
            height_int = int(height)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="width/height 必须为整数")
        if not (CAPTCHA_WIDTH_MIN <= width_int <= CAPTCHA_WIDTH_MAX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"width 必须在 {CAPTCHA_WIDTH_MIN}-{CAPTCHA_WIDTH_MAX} 之间",
            )
        if not (CAPTCHA_HEIGHT_MIN <= height_int <= CAPTCHA_HEIGHT_MAX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"height 必须在 {CAPTCHA_HEIGHT_MIN}-{CAPTCHA_HEIGHT_MAX} 之间",
            )
        if not _CAPTCHA_COLOR_PATTERN.match(color or ""):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="color 必须为 #RRGGBB 格式的十六进制颜色",
            )

        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        puzzle_size = 44
        max_target = width_int - puzzle_size - 8
        if max_target <= 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"验证码宽度需大于 {puzzle_size + 16}",
            )
        target_x = 8 + secrets.randbelow(max_target - 8 + 1)
        target_y = (height_int - puzzle_size) // 2

        bg_image, slider_image = self._render_captcha_images(
            width_int, height_int, target_x, target_y, puzzle_size
        )

        captcha_id = uuid4().hex
        cache_set(
            self._build_captcha_cache_key(captcha_id),
            json.dumps(
                {
                    "type": "slider",
                    "target_x": target_x,
                    "tolerance": tolerance,
                    "created_at": int(time.time() * 1000),
                },
                ensure_ascii=True,
            ),
            settings.CAPTCHA_EXPIRE_SECONDS,
        )
        # 不返回 targetX（答案）：仅返回带缺口的背景图与滑块图，前端视觉对齐
        return CaptchaResponse(
            captcha_id=captcha_id,
            data={
                "type": "slider",
                "bg": self._image_to_data_url(bg_image),
                "slider": self._image_to_data_url(slider_image),
                "sliderWidth": puzzle_size,
                "sliderY": target_y,
                "trackWidth": width_int,
                "tolerance": tolerance,
                "expireSeconds": settings.CAPTCHA_EXPIRE_SECONDS,
                "label": "拖动滑块对齐缺口完成验证",
            },
        )

    def captcha_check(self, captcha_id: str | None, verify_code: str | None) -> None:
        if not captcha_id or not verify_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不能为空")
        cache_key = self._build_captcha_cache_key(captcha_id)
        # 防重放：原子读取并删除（GETDEL），并发请求中仅一个能消费成功
        cached = cache_get_del(cache_key)
        if not cached:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        try:
            challenge = json.loads(cached)
            payload = json.loads(verify_code)
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        if challenge.get("type") != "slider":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        try:
            target_x = float(challenge["target_x"])
            tolerance = float(challenge["tolerance"])
            final_x = float(payload["x"])
            duration_ms = int(payload["duration"])
            track = payload["track"]
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        if abs(final_x - target_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if duration_ms < settings.CAPTCHA_SLIDER_MIN_DURATION_MS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证速度过快，请重试")
        if not isinstance(track, list) or len(track) < settings.CAPTCHA_SLIDER_MIN_TRACK_POINTS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")

        previous_x = -1.0
        backtrack_total = 0.0
        for point in track:
            if not isinstance(point, dict):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            try:
                current_x = float(point["x"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            if current_x < previous_x:
                backtrack = previous_x - current_x
                backtrack_total += backtrack
                if backtrack > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            previous_x = current_x

        if backtrack_total > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX * 2:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
        if abs(previous_x - final_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")

    def get_current_profile(self, user: User) -> CoolUserInfo:
        roles = get_user_roles(self.session, user.id)
        permissions = get_user_permissions(self.session, user.id)
        # 检查是否需要强制修改密码
        force_password_change = user.password_changed_at is None
        return self.build_user_info(
            user, roles=roles, permissions=permissions, force_password_change=force_password_change
        )

    def build_user_info(
        self, user: User, roles: list[Role], permissions: list[str], force_password_change: bool = False
    ) -> CoolUserInfo:
        return CoolUserInfo(
            user_id=user.id,
            username=user.username,
            nick_name=user.full_name,
            department_id=user.department_id,
            role_codes=[role.code for role in roles],
            permission=permissions,
            is_super_admin=user.is_super_admin,
            force_password_change=force_password_change,
        )

    def person(self, user: User) -> UserPersonRead:
        return UserPersonRead(
            id=user.id,
            created_at=user.created_at,
            updated_at=user.updated_at or user.created_at,
            department_id=user.department_id,
            full_name=user.full_name,
            username=user.username,
            password_version=user.password_version,
            nick_name=user.nick_name,
            head_img=user.head_img,
            phone=user.phone,
            email=user.email,
            remark=user.remark,
            is_active=user.is_active,
            is_super_admin=1 if user.is_super_admin else 0,
            is_manager=1 if user.is_manager else 0,
            is_department_leader=1 if user.is_department_leader else 0,
        )

    def person_update(self, user: User, payload: UserPersonUpdateRequest) -> dict:
        target = self.session.get(User, user.id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        if payload.password:
            if not payload.old_password:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不能为空")
            if not verify_password(payload.old_password, target.password_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
            # 验证新密码强度
            validate_password_strength(payload.password)
            target.password_hash = hash_password(payload.password)
            target.password_version += 1
            target.password_changed_at = datetime.now(timezone.utc)  # 记录密码修改时间

        if payload.nick_name is not None:
            target.nick_name = payload.nick_name
        if payload.head_img is not None:
            target.head_img = payload.head_img
        if payload.phone is not None:
            target.phone = payload.phone
        if payload.email is not None:
            target.email = payload.email
        if payload.remark is not None:
            target.remark = payload.remark

        target.updated_at = datetime.now(timezone.utc)
        self.session.add(target)
        self.session.commit()
        self.session.refresh(target)
        clear_login_caches(target.id)
        return {"success": True}

    def permmenu(self, user: User) -> dict:
        """
        获取权限与菜单（Loom 兼容格式）

        返回格式: {"perms": list[str], "menus": list[dict]}

        重要: 菜单必须返回扁平数组结构，而非树形嵌套结构！
        - Loom 前端期望所有菜单项在同一层级，通过 parentId 字段建立父子关系
        - 每个菜单项的 children 数组必须为空 []
        - 测试用例 test_permmenu_contains_flat_system_management_routes 依赖此结构
        - 不要修改为树形结构，否则会导致前端无法正确渲染菜单

        Args:
            user: 当前用户

        Returns:
            dict: 包含 perms (权限列表) 和 menus (扁平菜单数组) 的字典
        """
        permissions = get_user_permissions(self.session, user.id)

        # 获取树形结构的菜单
        menu_tree = MenuAdminService(self.session).current_tree(user)

        # 转换为 CoolMenuItem 并扁平化，符合 Loom 前端期望的扁平数组格式
        cool_menus = [self._build_cool_menu_item(menu) for menu in menu_tree]
        flat_menus = self._flatten_cool_menus(cool_menus)

        return {
            "perms": permissions,
            "menus": [item.model_dump(mode="json", by_alias=True) for item in flat_menus],
        }

    def _build_cool_menu_item(
        self, menu, name_map: dict[int, str] | None = None, children_override: list = None
    ) -> CoolMenuItem:
        type_mapping = {"group": 0, "menu": 1, "button": 2}

        # 处理可能的模型对象或字典
        m_id = getattr(menu, "id", None)
        parent_id = getattr(menu, "parent_id", None)
        name = getattr(menu, "name", "")
        path = getattr(menu, "path", None)
        permission = getattr(menu, "permission", None)
        menu_type = getattr(menu, "type", 1)
        sort_order = getattr(menu, "sort_order", 0)
        component = getattr(menu, "component", None)
        keep_alive = getattr(menu, "keep_alive", True)
        is_show = getattr(menu, "is_show", True)
        is_active = getattr(menu, "is_active", True)
        # 如果传入了 children_override（来自树处理），则优先使用
        if children_override is not None:
            children = children_override
        else:
            children = getattr(menu, "children", getattr(menu, "child_menus", []))

        parent_name = None
        if name_map and parent_id in name_map:
            parent_name = name_map[parent_id]
        elif parent_id:
            parent_name = getattr(menu, "parent_name", None)

        final_type = type_mapping.get(menu_type, menu_type if isinstance(menu_type, int) else 1)

        # 处理组件路径逻辑，防止前端 Vue Router 报 Invalid route component
        if final_type == 0:  # 目录类型
            component = None
        elif final_type == 1:  # 菜单类型
            if not component or (isinstance(component, str) and not component.strip()):
                # 如果是带子菜单的父级菜单但没有定义组件，通常需要 layout 承载
                component = "layout" if children else None

        return CoolMenuItem(
            id=m_id,
            parent_id=parent_id,
            parent_name=parent_name,
            name=name,
            path=path,
            permission=permission,
            type=final_type,
            sort_order=sort_order,
            component=component,
            icon=getattr(menu, "icon", None),
            keep_alive=keep_alive,
            is_show=is_show,
            is_active=is_active,
            child_menus=[
                (self._build_cool_menu_item(child, name_map=name_map) if children_override is None else child)
                for child in children
            ],
        )

    def _flatten_cool_menus(self, menus: list[CoolMenuItem]) -> list[CoolMenuItem]:
        """
        将树形菜单结构扁平化

        将嵌套的树形菜单结构转换为扁平数组，每个菜单项的 child_menus 被清空。
        这是 Loom 前端框架的硬性要求，前端需要通过 parentId 字段自行构建树形结构。

        注意: 不要修改此方法的返回格式，否则会导致前端菜单无法正确渲染。

        Args:
            menus: 树形嵌套的菜单列表

        Returns:
            扁平化的菜单列表，每个菜单项的 child_menus 为空数组
        """
        result: list[CoolMenuItem] = []

        def walk(items: list[CoolMenuItem]) -> None:
            for item in items:
                children = item.child_menus
                result.append(item.model_copy(update={"child_menus": []}))
                if children:
                    walk(children)

        walk(menus)
        return result

    @staticmethod
    def _build_captcha_cache_key(captcha_id: str) -> str:
        return f"verify:slider:{captcha_id}"

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

    def bootstrap_defaults(self) -> None:
        root_department = self.session.exec(select(Department).where(Department.name == "平台")).first()
        if not root_department:
            root_department = Department(name="平台", sort_order=0)
            self.session.add(root_department)
            self.session.commit()
            self.session.refresh(root_department)

        admin_role = self.session.exec(select(Role).where(Role.code == "admin")).first()
        if not admin_role:
            admin_role = Role(name="系统管理员", code="admin", label="admin", data_scope="all")
            self.session.add(admin_role)
            self.session.commit()
            self.session.refresh(admin_role)

        operator_role = self.session.exec(select(Role).where(Role.code == "task_operator")).first()
        if not operator_role:
            operator_role = Role(
                name="任务操作员",
                code="task_operator",
                label="task_operator",
                data_scope="self",
            )
            self.session.add(operator_role)
            self.session.commit()
            self.session.refresh(operator_role)

        role_map = {
            admin_role.code: admin_role,
            operator_role.code: operator_role,
        }

        navigation_definitions = load_menu_manifest_items()

        all_valid_codes: set[str] = {item.code for item in navigation_definitions}
        managed_permissions: set[str] = {item.permission for item in navigation_definitions if item.permission}
        managed_paths: set[str] = {item.path for item in navigation_definitions if item.path}

        menus_by_code: dict[str, Menu] = {}
        for item in navigation_definitions:
            menu = self.session.exec(select(Menu).where(Menu.code == item.code)).first()
            if not menu:
                menu = Menu(
                    name=item.name,
                    code=item.code,
                    type=item.type,
                    path=item.path,
                    component=item.component,
                    icon=item.icon,
                    keep_alive=item.keep_alive,
                    is_show=item.is_show,
                    sort_order=item.sort_order,
                    is_active=item.is_active,
                    permission=item.permission,
                )
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)
            else:
                menu.name = item.name
                menu.type = item.type
                menu.path = item.path
                menu.component = item.component
                menu.icon = item.icon
                menu.keep_alive = item.keep_alive
                menu.is_show = item.is_show
                menu.sort_order = item.sort_order
                menu.is_active = item.is_active
                menu.permission = item.permission
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)
            menus_by_code[item.code] = menu

        for item in navigation_definitions:
            menu = menus_by_code[item.code]
            parent_code = item.parent_code
            if parent_code:
                parent_menu = menus_by_code[parent_code]
                desired_parent_id = parent_menu.id
            else:
                # parent_code 为空表示该菜单应作为顶级节点；
                # 需主动清空已存在的 parent_id，否则历史挂载关系无法回滚
                # （例如将分组从“系统管理”下提升为一级菜单）
                desired_parent_id = None
            if menu.parent_id != desired_parent_id:
                menu.parent_id = desired_parent_id
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)

        for item in navigation_definitions:
            menu = menus_by_code[item.code]
            for role_code in item.role_codes:
                role = role_map.get(role_code)
                if role and role.id is not None and menu.id is not None:
                    self._ensure_role_menu_link(role.id, menu.id)

        # 清理数据库中不再存在（既不在 JSON Manifest 中，也不在控制器扫描结果中）的权限记录
        all_db_menus = self.session.exec(select(Menu)).all()
        for db_menu in all_db_menus:
            if db_menu.code not in all_valid_codes and self._is_system_managed_menu(
                db_menu, managed_permissions, managed_paths
            ):
                # 删除与之关联的角色绑定，防止外键约束错误
                links = self.session.exec(select(RoleMenuLink).where(RoleMenuLink.menu_id == db_menu.id)).all()
                for link in links:
                    self.session.delete(link)
                self.session.delete(db_menu)
        self.session.commit()

        if admin_role.id is not None and root_department.id is not None:
            self._ensure_role_department_link(admin_role.id, root_department.id)
        if operator_role.id is not None and root_department.id is not None:
            self._ensure_role_department_link(operator_role.id, root_department.id)

        admin_user = self.session.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
        if not admin_user:
            admin_user = User(
                username=settings.DEFAULT_ADMIN_USERNAME.strip(),
                full_name=settings.DEFAULT_ADMIN_NAME,
                password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD.strip()),
                department_id=root_department.id,
                is_super_admin=True,
                is_manager=True,
                is_department_leader=True,
            )
            self.session.add(admin_user)
            self.session.commit()
            self.session.refresh(admin_user)

        if admin_user.id is not None and admin_role.id is not None:
            self._ensure_user_role_link(admin_user.id, admin_role.id)

        # 同步完成后清理全站权限缓存，确保新菜单生效
        all_user_ids = self.session.exec(select(User.id)).all()
        clear_login_caches_for_users(all_user_ids)

    def _ensure_user_role_link(self, user_id: int, role_id: int) -> None:
        link = self.session.exec(
            select(UserRoleLink).where(UserRoleLink.user_id == user_id, UserRoleLink.role_id == role_id)
        ).first()
        if not link:
            self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))
            self.session.commit()

    def _ensure_role_menu_link(self, role_id: int, menu_id: int) -> None:
        link = self.session.exec(
            select(RoleMenuLink).where(RoleMenuLink.role_id == role_id, RoleMenuLink.menu_id == menu_id)
        ).first()
        if not link:
            self.session.add(RoleMenuLink(role_id=role_id, menu_id=menu_id))
            self.session.commit()

    def _ensure_role_department_link(self, role_id: int, department_id: int) -> None:
        link = self.session.exec(
            select(RoleDepartmentLink).where(
                RoleDepartmentLink.role_id == role_id, RoleDepartmentLink.department_id == department_id
            )
        ).first()
        if not link:
            self.session.add(RoleDepartmentLink(role_id=role_id, department_id=department_id))
            self.session.commit()

    def _check_login_risk(self, account: str, ip: str) -> str | None:
        if cache_get(self._build_account_lock_key(account)):
            return "账号已被临时锁定，请稍后再试"
        if cache_get(self._build_ip_lock_key(ip)):
            return "当前IP请求过于频繁，请稍后再试"
        return None

    def _mark_login_failure(self, account: str, ip: str) -> int:
        account_failures = self._increase_counter(
            self._build_account_fail_key(account), settings.BASE_LOGIN_FAIL_WINDOW
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

    def _clear_login_failure(self, account: str, ip: str) -> None:
        cache_delete(
            self._build_account_fail_key(account),
            self._build_ip_fail_key(ip),
            self._build_account_lock_key(account),
            self._build_ip_lock_key(ip),
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

    @staticmethod
    def _is_system_managed_menu(menu: Menu, managed_permissions: set[str], managed_paths: set[str]) -> bool:
        if menu.permission and menu.permission in managed_permissions:
            return True
        if menu.path and menu.path in managed_paths:
            return True
        code = menu.code or ""
        return any(code.startswith(prefix) for prefix in SYSTEM_MANAGED_CODE_PREFIXES)


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
