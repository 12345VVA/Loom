"""
Base 模块健康检查
"""
from app.core.config import settings
from app.core.database import engine
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get
from app.modules.base.service.cache_service import get_redis_client
from sqlalchemy import text


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
        checks = {
            "database": _check_database(),
            "redis": _check_redis(),
        }
        return {
            "status": "healthy" if all(item["status"] in {"ok", "skipped"} for item in checks.values()) else "degraded",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "module": "base",
            "checks": checks,
        }


router = BaseHealthController.router


def _check_database() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _check_redis() -> dict:
    client = get_redis_client()
    if client is None:
        return {"status": "skipped", "message": "memory fallback active"}
    try:
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
