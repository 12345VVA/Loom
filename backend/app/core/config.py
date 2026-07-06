"""
应用配置
"""

import json
from typing import Any
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用设置"""

    # 基础配置
    APP_NAME: str  # 启动时自动从 .env 中读取
    APP_VERSION: str  # 启动时自动从 .env 中读取
    DEBUG: bool  # 启动时自动从 .env 中读取
    LOG_LEVEL: str = ""
    LOG_DIR: str = "logs"
    LOG_RETENTION_DAYS: int = 30
    EPS_ENABLED: str = ""

    # 服务器配置
    HOST: str  # 启动时自动从 .env 中读取
    PORT: int  # 启动时自动从 .env 中读取

    # 数据库配置
    # DATABASE_URL 直接填写完整连接串；留空时由下方 SQL_* 字段拼装 PostgreSQL 连接串
    DATABASE_URL: str = ""
    # 分离式 PostgreSQL 连接配置（DATABASE_URL 为空且 SQL_HOST 非空时启用）
    SQL_HOST: str = ""
    SQL_PORT: int = 5432
    SQL_DATABASE: str = ""
    SQL_USER: str = ""
    SQL_PASSWORD: str = ""

    # Redis 配置
    REDIS_URL: str  # 启动时自动从 .env 中读取

    # Celery 配置
    CELERY_BROKER_URL: str  # 启动时自动从 .env 中读取
    CELERY_RESULT_BACKEND: str  # 启动时自动从 .env 中读取

    # 工作流引擎
    # checkpoint 默认 sqlite：保证 Celery 多 Worker / 重启后 paused 实例可恢复（memory 仅用于单进程演示）
    WORKFLOW_CHECKPOINT_BACKEND: str = "sqlite"  # "memory" | "sqlite" | "postgres"
    WORKFLOW_NODE_TEST_TIMEOUT: int = 180  # 单节点测试超时秒数（LLM 节点常需 60-180 秒）
    WORKFLOW_NODE_TIMEOUT: int = 600  # 正式执行单节点超时秒数（比 30 分钟硬上限短，留足图像节点空间）
    # 节点级自动重试：失败后按指数退避重试，覆盖 LLM / 外部 API 临时故障
    # max_attempts 含首次（1=不重试）；delay = base * 2^(attempt-1)；节点 config 可覆盖（retry_max_attempts / retry_backoff_base）
    WORKFLOW_NODE_RETRY_MAX_ATTEMPTS: int = 1
    WORKFLOW_NODE_RETRY_BACKOFF_BASE: float = 2.0
    # 评测系统 llm_judge 兜底模型 Profile（用例未单独配置 judge_profile_code 时使用；空表示未配置）
    WORKFLOW_EVAL_JUDGE_PROFILE: str = ""
    # 评测回归对比：单 case score 变化阈值（B 相对 A 超此值视为退化/改善）
    WORKFLOW_EVAL_REGRESSION_THRESHOLD: float = 0.1
    # 评测回归对比：整体 score diff 的 bootstrap 重采样次数（CI 跨 0 即不显著）
    WORKFLOW_EVAL_BOOTSTRAP_SAMPLES: int = 1000
    # 节点载荷冷热分离阈值（T8）：单字段字节超此值则落对象存储、主表存引用
    PAYLOAD_STORAGE_THRESHOLD: int = 32 * 1024

    # OpenAI / Ollama 配置
    OPENAI_API_KEY: str  # 启动时自动从 .env 中读取
    OPENAI_BASE_URL: str  # 启动时自动从 .env 中读取
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = ""
    SECRET_ENCRYPTION_KEY: str = ""
    BACKEND_URL: str = ""
    EXTERNAL_URL: str = ""

    # 认证配置
    JWT_SECRET_KEY: str  # 启动时自动从 .env 中读取
    JWT_ALGORITHM: str  # 启动时自动从 .env 中读取
    ACCESS_TOKEN_EXPIRE_MINUTES: int  # 启动时自动从 .env 中读取
    REFRESH_TOKEN_EXPIRE_DAYS: int  # 启动时自动从 .env 中读取
    # 专用下载令牌有效期（秒）：用于 /uploads 资源访问，短 TTL 隔离 access token 泄露面
    DOWNLOAD_TOKEN_EXPIRE_SECONDS: int = 300
    ADMIN_SSO_ENABLED: bool = False
    ADMIN_CAPTCHA_ENABLED: bool = False
    CAPTCHA_EXPIRE_SECONDS: int = 120
    CAPTCHA_SLIDER_TOLERANCE: int = 12
    CAPTCHA_SLIDER_MIN_DURATION_MS: int = 450
    CAPTCHA_SLIDER_MIN_TRACK_POINTS: int = 6
    CAPTCHA_SLIDER_MAX_BACKTRACK_PX: int = 8
    BASE_LOGIN_FAIL_WINDOW: int = 15 * 60
    BASE_LOGIN_ACCOUNT_FAIL_MAX: int = 5
    BASE_LOGIN_IP_FAIL_MAX: int = 20
    BASE_LOGIN_LOCK_TIME: int = 15 * 60
    DEFAULT_ADMIN_USERNAME: str  # 启动时自动从 .env 中读取
    DEFAULT_ADMIN_PASSWORD: str  # 启动时自动从 .env 中读取
    DEFAULT_ADMIN_NAME: str  # 启动时自动从 .env 中读取

    # 文件上传安全配置
    UPLOAD_MAX_SIZE_MB: int = 10  # 单文件最大 MB
    # 默认白名单不含 .svg：SVG 可内嵌 <script> 导致存储型 XSS，如需上传须显式配置并另行处理
    UPLOAD_ALLOWED_EXTENSIONS: str = (
        ".jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.rar,.txt,.csv,.json,.mp4,.mp3"
    )
    STORAGE_PROVIDER: str = "local"
    MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB: int = 100
    MEDIA_REMOTE_DOWNLOAD_TIMEOUT_SECONDS: int = 30
    MEDIA_REMOTE_ALLOWED_HOSTS: str = "*.volces.com"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "auto"
    S3_PUBLIC_BASE_URL: str = ""

    # API 限流配置
    RATE_LIMIT_ENABLED: bool = True  # 是否启用全局限流
    RATE_LIMIT_DEFAULT: int = 120  # 默认每分钟请求数上限
    RATE_LIMIT_ADMIN: int = 60  # /admin 前缀每分钟上限
    RATE_LIMIT_OPEN: int = 30  # 公开接口（登录等）每分钟上限
    RATE_LIMIT_WHITELIST_PATHS: str = "/docs,/redoc,/openapi.json,/health"  # 豁免限流的路径

    # 可信反向代理链配置
    # 逗号分隔的可信代理 IP 列表（如 "127.0.0.1,10.0.0.2"）；为空表示不信任任何代理，
    # 此时 _get_client_ip / _get_request_ip 直接使用 socket 对端 IP，忽略 X-Forwarded-For。
    # 配置后，X-Forwarded-For 将从右向左跳过可信代理，取第一个非可信 IP 作为真实客户端 IP。
    TRUSTED_PROXIES: str = ""

    # TaskInvoker 显式白名单：逗号分隔的 "service_key:method" 列表（如 "task.info:rebuild"）。
    # 配置后仅允许列出的服务方法被定时任务调用（fail-closed，未列出即拒绝）；
    # 留空则允许所有已扫描 service 的公开（非下划线）方法——此时白名单仍生效，
    # 便于审计与未来收窄，而不是形同虚设。
    TASK_ALLOWED_SERVICES: str = ""

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
    # 跳过启动时自动补建索引（CREATE INDEX IF NOT EXISTS）。
    # Field(index=True) 仅对 create_all 新建表生效，现有库不会自动补索引；_ensure_indexes 为现有库补齐查询关键索引。
    # 生产 PostgreSQL 大表建议由 DBA 在维护窗口用 CREATE INDEX CONCURRENTLY 建立后置 True，避免启动时锁表。
    SKIP_INDEX_ENSURE: bool = False
    # anyio 线程池上限：承载 offload 到线程池的同步阻塞调用（同步 DB/HTTP service、同步 def 路由）。
    # Starlette 默认 40，调大以支撑更多并发慢请求；超出此值的请求会排队而非挂起事件循环。
    ASYNC_THREAD_POOL_SIZE: int = 100

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

    @model_validator(mode="after")
    def _enforce_production_csrf(self) -> "Settings":
        """生产环境（DEBUG=False）强制开启 CSRF Origin 校验。

        即使 .env 中显式设置 ADMIN_CSRF_ORIGIN_CHECK_ENABLED=False，
        生产环境也会被覆盖为 True，防止运维误关闭。
        """
        if not self.DEBUG and not self.ADMIN_CSRF_ORIGIN_CHECK_ENABLED:
            self.ADMIN_CSRF_ORIGIN_CHECK_ENABLED = True
        return self

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        """DATABASE_URL 留空且配置了 SQL_HOST 时，拼装 PostgreSQL(psycopg3) 连接串。

        用户名/密码中的特殊字符会做 URL 编码（如 `@` -> `%40`），
        避免破坏连接串解析。两者均未配置时抛出明确错误。
        """
        if not self.DATABASE_URL and self.SQL_HOST:
            auth = ""
            if self.SQL_USER:
                password = quote_plus(self.SQL_PASSWORD) if self.SQL_PASSWORD else ""
                auth = f"{quote_plus(self.SQL_USER)}:{password}@"
            self.DATABASE_URL = (
                f"postgresql+psycopg://{auth}{self.SQL_HOST}:{self.SQL_PORT}/{self.SQL_DATABASE}"
            )
        if not self.DATABASE_URL:
            raise ValueError(
                "数据库未配置：请设置 DATABASE_URL，或通过 "
                "SQL_HOST/SQL_PORT/SQL_DATABASE/SQL_USER/SQL_PASSWORD 拼装 PostgreSQL 连接"
            )
        return self

    @property
    def effective_log_level(self) -> str:
        """应用日志级别；未显式设置 LOG_LEVEL 时兼容旧 DEBUG 行为。"""
        value = (self.LOG_LEVEL or "").strip().upper()
        if value:
            return value
        return "DEBUG" if self.DEBUG else "INFO"

    @property
    def db_echo_enabled(self) -> bool:
        """只有有效日志级别为 DEBUG 时才输出 SQL 查询日志。"""
        return self.effective_log_level == "DEBUG"

    @property
    def captcha_enabled(self) -> bool:
        """登录验证码开关：
        - 生产环境（DEBUG=False）强制启用，忽略 .env 配置；
        - 本地/测试（DEBUG=True）按 ADMIN_CAPTCHA_ENABLED 配置（默认关闭便于调试，
          pytest 经 conftest 设 True 仍可启用以覆盖验证码校验逻辑）。
        """
        if not self.DEBUG:
            return True
        return self.ADMIN_CAPTCHA_ENABLED

    @property
    def cors_origins_list(self) -> list[str]:
        """解析 CORS origins"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return ["http://localhost:5173"]

    @property
    def cors_methods_list(self) -> list[str]:
        return self._parse_csv_or_json(self.CORS_ALLOW_METHODS, ["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    @property
    def cors_headers_list(self) -> list[str]:
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

    @property
    def trusted_proxies_list(self) -> list[str]:
        """解析可信代理 IP 列表；空字符串返回空列表（不信任任何代理）。"""
        return self._parse_csv_or_json(self.TRUSTED_PROXIES, [])

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

    # extra="ignore"：容许 .env 中存在未在 Settings 声明的键（如临时调试变量），不再因 forbid 而启动失败
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
