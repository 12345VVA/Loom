"""
Base 模块 App Scope 健康检查
"""
from app.core.config import settings
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from fastapi import Depends


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="health",
        scope="app",
        service=object,
        tags=("base", "health"),
        actions=(),
    )
)
class BaseAppHealthController(BaseController):
    @Get("/ping", summary="App 健康检查", anonymous=True)
    async def health_check(self) -> dict:
        return {
            "status": "healthy",
            "scope": "app",
            "app": settings.APP_NAME,
        }

    @Get("/secure", summary="App 鉴权检查")
    async def secure(self, current_user: User = Depends(get_current_user)) -> dict:
        return {
            "status": "ok",
            "scope": "app",
            "user": current_user.username,
        }


router = BaseAppHealthController.router
