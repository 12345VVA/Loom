"""
Base 模块开放接口
"""

from fastapi import Depends, Request, Response
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import (
    CaptchaResponse,
    CoolLoginResponse,
    LoginRequest,
    RefreshTokenRequest,
    User,
)
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.eps_service import EpsService
from app.modules.base.service.security_service import get_current_user

# refreshToken HttpOnly cookie 配置
# - HttpOnly：禁止 JS 读取，防 XSS 凭证失窃
# - Secure：生产环境强制启用（仅 HTTPS 传输）
# - SameSite=Lax：防 CSRF 跨站提交
# - Path=/admin/base/open：仅开放接口路径携带，缩小 cookie 暴露面
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/admin/base/open"


def _set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    """在响应中设置 refreshToken HttpOnly cookie。"""
    response.set_cookie(
        REFRESH_TOKEN_COOKIE_NAME,
        refresh_token,
        path=REFRESH_TOKEN_COOKIE_PATH,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _clear_refresh_token_cookie(response: Response) -> None:
    """清除 refreshToken cookie。"""
    response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, path=REFRESH_TOKEN_COOKIE_PATH)


def _read_refresh_token_cookie(request: Request) -> str | None:
    """从请求 cookie 中读取 refreshToken。"""
    return request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="open",
        scope="admin",
        service=AuthService,
        tags=("base", "open"),
        actions=(),
    )
)
class BaseOpenController(BaseController):
    @Post("/login", summary="账号密码登录", anonymous=True)
    def login(
        self,
        request: Request,
        payload: LoginRequest,
        response: Response,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        result = service.login(payload, request=request)
        # 通过 HttpOnly cookie 下发 refreshToken，前端不再存储
        _set_refresh_token_cookie(response, result.refresh_token)
        return result

    @Post("/refresh", summary="刷新访问令牌", anonymous=True)
    def refresh_token(
        self,
        request: Request,
        payload: RefreshTokenRequest,
        response: Response,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        # 优先从 HttpOnly cookie 读取 refreshToken，兼容 body 传递
        token_value = _read_refresh_token_cookie(request) or payload.token_value
        result = service.refresh_token_by_value(token_value)
        _set_refresh_token_cookie(response, result.refresh_token)
        return result

    @Get("/captcha", summary="验证码", anonymous=True)
    def captcha(
        self,
        width: int = 150,
        height: int = 80,
        color: str = "#333333",
        session: Session = Depends(get_session),
    ) -> CaptchaResponse:
        service = AuthService(session)
        return service.captcha(width, height, color)

    @Get("/config", summary="登录页公开配置", anonymous=True)
    def config(self) -> dict:
        return {"captchaEnabled": bool(settings.ADMIN_CAPTCHA_ENABLED)}

    @Post("/refreshToken", summary="刷新访问令牌", anonymous=True)
    def refresh_token_compat(
        self,
        request: Request,
        payload: RefreshTokenRequest,
        response: Response,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        token_value = _read_refresh_token_cookie(request) or payload.token_value
        result = service.refresh_token_by_value(token_value)
        _set_refresh_token_cookie(response, result.refresh_token)
        return result

    @Post(
        "/logout",
        summary="退出登录并清理服务端登录态",
        permission="base:session:logout",
        role_codes=("admin", "task_operator"),
    )
    def logout(
        self,
        request: Request,
        response: Response,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = AuthService(session)
        service.logout(current_user, request=request)
        # 登出时清除 refreshToken cookie
        _clear_refresh_token_cookie(response)
        return {"success": True}

    @Get("/eps", summary="导出 EPS 扫描元数据", anonymous=True)
    def eps(self, request: Request) -> dict:
        return EpsService(request.app).export_admin()


router = BaseOpenController.router
