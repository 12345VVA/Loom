"""
Base 模块开放接口
"""
from fastapi import Depends, Request
from sqlmodel import Session

from app.core.database import get_session
from app.core.config import settings
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import CaptchaResponse, CoolLoginResponse, LoginRequest, RefreshTokenRequest, User
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.eps_service import EpsService
from app.modules.base.service.security_service import get_current_user


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
    async def login(
        self,
        request: Request,
        payload: LoginRequest,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        return service.login(payload, request=request)

    @Post("/refresh", summary="刷新访问令牌", anonymous=True)
    async def refresh_token(
        self,
        payload: RefreshTokenRequest,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        return service.refresh_token(payload)

    @Get("/captcha", summary="验证码", anonymous=True)
    async def captcha(
        self,
        width: int = 150,
        height: int = 50,
        color: str = "#333",
        session: Session = Depends(get_session),
    ) -> CaptchaResponse:
        service = AuthService(session)
        return service.captcha(width, height, color)

    @Post("/refreshToken", summary="刷新访问令牌", anonymous=True)
    async def refresh_token_compat(
        self,
        payload: RefreshTokenRequest,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        return service.refresh_token(payload)

    @Get("/refreshToken", summary="刷新访问令牌", anonymous=True)
    async def refresh_token_get(
        self,
        refreshToken: str,
        session: Session = Depends(get_session),
    ) -> CoolLoginResponse:
        service = AuthService(session)
        return service.refresh_token(RefreshTokenRequest(refreshToken=refreshToken))

    @Post(
        "/logout",
        summary="退出登录并清理服务端登录态",
        permission="base:session:logout",
        role_codes=("admin", "task_operator"),
    )
    async def logout(
        self,
        request: Request,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = AuthService(session)
        service.logout(current_user, request=request)
        return {"success": True}

    @Get("/eps", summary="导出 EPS 扫描元数据", anonymous=True)
    async def eps(self, request: Request) -> dict:
        return EpsService(request.app).export_admin()


router = BaseOpenController.router
