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

    # API 限流配置
    RATE_LIMIT_ENABLED: bool = True                    # 是否启用全局限流
    RATE_LIMIT_DEFAULT: int = 120                      # 默认每分钟请求数上限
    RATE_LIMIT_ADMIN: int = 60                         # /admin 前缀每分钟上限
    RATE_LIMIT_OPEN: int = 30                          # 公开接口（登录等）每分钟上限
    RATE_LIMIT_WHITELIST_PATHS: str = "/docs,/redoc,/openapi.json,/health"  # 豁免限流的路径

    # CORS 配置
    CORS_ORIGINS: str  # 启动时自动从 .env 中读取

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
    def eps_enabled(self) -> bool:
        raw = self.EPS_ENABLED
        if raw == "":
            return self.DEBUG
        lowered = str(raw).strip().lower()
        return lowered in {"1", "true", "yes", "on"}

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
