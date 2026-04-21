"""
Base 模块配置
"""
from sqlmodel import Session

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.framework.middleware.operation_log import OperationLogMiddleware
from app.framework.middleware.rate_limit import RateLimitMiddleware
from app.framework.middleware.response_envelope import ResponseEnvelopeMiddleware
from app.framework.middleware.scope_authority import AdminAuthorityMiddleware, AiApiAuthorityMiddleware, AppAuthorityMiddleware
from app.modules.base.service.auth_service import AuthService
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="base",
    label="基础权限模块",
    description="基础的权限管理功能，包括登录、权限校验和 EPS 导出",
    order=10,
    scopes=("admin",),
    bootstrap="app.modules.base.config.bootstrap",
    middlewares=(ModuleAccessMiddleware,),
    global_middlewares=(
        RateLimitMiddleware,
        ResponseEnvelopeMiddleware,
        OperationLogMiddleware,
        AiApiAuthorityMiddleware,
        AppAuthorityMiddleware,
        AdminAuthorityMiddleware,
    ),
    config_namespace="BASE",
    init_db_file="init_db.py",
    init_menu_file="menu.json",
    admin_whitelist=(
        "/admin/base/open/login",
        "/admin/base/open/refresh",
        "/admin/base/open/refreshToken",
        "/admin/base/open/captcha",
        "/admin/base/open/eps",
        "/admin/base/health/ping",
    ),
)


def bootstrap(session: Session) -> None:
    """初始化基础权限数据"""
    AuthService(session).bootstrap_defaults()
