"""
Base 模块健康检查
"""
from app.core.config import settings
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="health",
        scope="admin",
        service=object,
        tags=("base", "health"),
        actions=(),
    )
)
class BaseHealthController(BaseController):
    @Get("/ping", summary="健康检查接口", anonymous=True)
    async def health_check(self) -> dict:
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "module": "base",
        }


router = BaseHealthController.router
