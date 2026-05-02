"""
启动配置校验。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, settings


@dataclass(frozen=True)
class StartupCheckResult:
    level: str
    key: str
    message: str


def validate_startup_settings(config: Settings = settings) -> list[StartupCheckResult]:
    """返回当前配置的风险清单；生产模式错误由调用方决定是否阻断启动。"""
    results: list[StartupCheckResult] = []
    is_prod = not config.DEBUG

    if len(config.JWT_SECRET_KEY or "") < 32:
        results.append(StartupCheckResult("error" if is_prod else "warning", "JWT_SECRET_KEY", "JWT 密钥长度建议至少 32 字符"))

    if is_prod and config.DEFAULT_ADMIN_PASSWORD in {"admin", "123456", "12345678", "password", "Passw0rd!"}:
        results.append(StartupCheckResult("error", "DEFAULT_ADMIN_PASSWORD", "生产环境不能使用默认或弱管理员密码"))

    origins = config.cors_origins_list
    if is_prod and ("*" in origins or not origins):
        results.append(StartupCheckResult("error", "CORS_ORIGINS", "生产环境必须显式配置可信 CORS 来源"))

    if is_prod and config.DATABASE_URL.startswith("sqlite"):
        results.append(StartupCheckResult("warning", "DATABASE_URL", "生产环境建议使用 PostgreSQL 或 MySQL，不建议使用 SQLite"))

    if is_prod and not config.REDIS_URL:
        results.append(StartupCheckResult("error", "REDIS_URL", "生产环境必须配置 Redis"))

    if is_prod and not config.CELERY_BROKER_URL:
        results.append(StartupCheckResult("error", "CELERY_BROKER_URL", "生产环境必须配置 Celery broker"))

    if not config.SECRET_ENCRYPTION_KEY:
        results.append(StartupCheckResult("error" if is_prod else "warning", "SECRET_ENCRYPTION_KEY", "模型供应商密钥加密需要配置 SECRET_ENCRYPTION_KEY"))
    elif len(config.SECRET_ENCRYPTION_KEY) < 32:
        results.append(StartupCheckResult("error" if is_prod else "warning", "SECRET_ENCRYPTION_KEY", "SECRET_ENCRYPTION_KEY 长度建议至少 32 字符"))

    return results


def assert_startup_settings(config: Settings = settings) -> None:
    errors = [item for item in validate_startup_settings(config) if item.level == "error"]
    if errors:
        detail = "; ".join(f"{item.key}: {item.message}" for item in errors)
        raise RuntimeError(f"启动配置校验失败: {detail}")
