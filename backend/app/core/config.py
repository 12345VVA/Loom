"""
应用配置
"""
from typing import Any

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json
import secrets


class Settings(BaseSettings):
    """应用设置"""

    # 基础配置
    APP_NAME: str  # 启动时自动从 .env 中读取
    APP_VERSION: str  # 启动时自动从 .env 中读取
    DEBUG: bool  # 启动时自动从 .env 中读取
    EPS_ENABLED: str = ""

    # 服务器配置
    HOST: str  # 启动时自动从 .env 中读取
    PORT: int  # 启动时自动从 .env 中读取

    # 数据库配置
    DATABASE_URL: str  # 启动时自动从 .env 中读取

    # Redis 配置
    REDIS_URL: str  # 启动时自动从 .env 中读取

    # Celery 配置
    CELERY_BROKER_URL: str  # 启动时自动从 .env 中读取
    CELERY_RESULT_BACKEND: str  # 启动时自动从 .env 中读取

    # OpenAI / Ollama 配置
    OPENAI_API_KEY: str  # 启动时自动从 .env 中读取
    OPENAI_BASE_URL: str  # 启动时自动从 .env 中读取

    # 认证配置
    JWT_SECRET_KEY: str # 启动时自动从 .env 中读取
    JWT_ALGORITHM: str  # 启动时自动从 .env 中读取
    ACCESS_TOKEN_EXPIRE_MINUTES: int  # 启动时自动从 .env 中读取
    REFRESH_TOKEN_EXPIRE_DAYS: int  # 启动时自动从 .env 中读取
    ADMIN_SSO_ENABLED: bool = False
    ADMIN_CAPTCHA_ENABLED: bool = True
    CAPTCHA_EXPIRE_SECONDS: int = 1800
    BASE_LOGIN_FAIL_WINDOW: int = 15 * 60
    BASE_LOGIN_ACCOUNT_FAIL_MAX: int = 5
    BASE_LOGIN_IP_FAIL_MAX: int = 20
    BASE_LOGIN_LOCK_TIME: int = 15 * 60
    DEFAULT_ADMIN_USERNAME: str  # 启动时自动从 .env 中读取
    DEFAULT_ADMIN_PASSWORD: str  # 启动时自动从 .env 中读取
    DEFAULT_ADMIN_NAME: str  # 启动时自动从 .env 中读取

    # 文件上传安全配置
    UPLOAD_MAX_SIZE_MB: int = 10                       # 单文件最大 MB
    UPLOAD_ALLOWED_EXTENSIONS: str = ".jpg,.jpeg,.png,.gif,.webp,.svg,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.rar,.txt,.csv,.json,.mp4,.mp3"
    STORAGE_PROVIDER: str = "local"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "auto"
    S3_PUBLIC_BASE_URL: str = ""

    # API 限流配置
    RATE_LIMIT_ENABLED: bool = True                    # 是否启用全局限流
    RATE_LIMIT_DEFAULT: int = 120                      # 默认每分钟请求数上限
    RATE_LIMIT_ADMIN: int = 60                         # /admin 前缀每分钟上限
    RATE_LIMIT_OPEN: int = 30                          # 公开接口（登录等）每分钟上限
    RATE_LIMIT_WHITELIST_PATHS: str = "/docs,/redoc,/openapi.json,/health"  # 豁免限流的路径

    # CORS 配置
    CORS_ORIGINS: str  # 启动时自动从 .env 中读取
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,X-Requested-With,X-Device-Id,X-Request-Id,token,x-token"
    ADMIN_CSRF_ORIGIN_CHECK_ENABLED: bool = False

    # 中间件/启动配置
    RESPONSE_ENVELOPE_MAX_BYTES: int = 2 * 1024 * 1024
    MODULE_LOAD_STRICT: bool = True
    METRICS_ENABLED: bool = False
    API_VERSION_PREFIX_ENABLED: bool = False
    API_VERSION_PREFIX: str = "/api/v1"

    # 密码与会话
    PASSWORD_PBKDF2_ITERATIONS: int = 210_000
    ADMIN_SESSION_MAX_CONCURRENT: int = 0

    # 数据库连接池
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> bool:
        """兼容 release/development 等环境变量写法"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if lowered in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return bool(value)

    @property
    def cors_origins_list(self) -> List[str]:
        """解析 CORS origins"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except:
            return ["http://localhost:5173"]

    @property
    def cors_methods_list(self) -> List[str]:
        return self._parse_csv_or_json(self.CORS_ALLOW_METHODS, ["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    @property
    def cors_headers_list(self) -> List[str]:
        return self._parse_csv_or_json(
            self.CORS_ALLOW_HEADERS,
            ["Authorization", "Content-Type", "X-Requested-With", "X-Device-Id", "X-Request-Id", "token", "x-token"],
        )

    @property
    def eps_enabled(self) -> bool:
        raw = self.EPS_ENABLED
        if raw == "":
            return self.DEBUG
        lowered = str(raw).strip().lower()
        return lowered in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_csv_or_json(value: str, fallback: list[str]) -> list[str]:
        if not value:
            return fallback
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items or fallback

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
