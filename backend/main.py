"""
Loom API - FastAPI 主入口
"""

import os
import re
import sys
import warnings

# pydantic 在运行时为第三方库（langgraph/langchain 工具与 agent 等）生成 schema 时，会因
# Field(alias=...) 被用在 Annotated/union 上而抛出 UnsupportedFieldAttributeWarning。该提示对功能
# 无影响（pydantic 自述该 alias 本就不生效），项目代码经排查不含此类用法，仅精准过滤该条消息以保持日志整洁。
warnings.filterwarnings(
    "ignore",
    message=r"The 'alias' attribute with value .* was provided to the `Field\(\)` function.*",
)

from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError as DBOperationalError

load_dotenv()

from app.core.config import settings
from app.core.database import Session, engine, get_session, init_db
from app.core.logging import configure_logging
from app.core.startup_checks import assert_startup_settings, validate_startup_settings
from app.framework.api.exception_handlers import register_exception_handlers
from app.framework.middleware.admin_csrf import assert_cors_configuration
from app.framework.middleware.metrics import render_metrics
from app.framework.middleware.module_runtime import PrefixScopedMiddleware
from app.framework.router import create_api_router
from app.framework.storage import DEFAULT_UPLOAD_DIR
from app.modules import (
    bootstrap_modules,
    load_global_middlewares,
    load_module_middlewares,
    load_module_runtime_infos,
    load_scope_whitelists,
)
from app.modules.base.service.authority_service import get_user_from_download_token, is_super_admin
from app.modules.base.service.cache_service import get_redis_client
from app.modules.media.model.media import MediaAsset
from sqlmodel import select

configure_logging(
    log_level=settings.effective_log_level,
    log_dir=settings.LOG_DIR,
    retention_days=settings.LOG_RETENTION_DAYS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 调大 anyio 线程池上限：承载 offload 的同步阻塞调用（同步 DB/HTTP service、同步 def 路由）
    anyio.to_thread.current_default_thread_limiter().total = settings.ASYNC_THREAD_POOL_SIZE
    # 启动时执行
    assert_cors_configuration(allow_credentials=True, allow_origins=settings.cors_origins_list)
    assert_startup_settings()
    try:
        init_db()
    except DBOperationalError as exc:
        # 数据库连接失败：给出简洁提示并直接退出，避免框架/驱动抛出冗长的错误链
        print(
            "\n[启动失败] 数据库连接失败，请确认数据库服务已启动、网络可达，"
            f"且 .env 中 DATABASE_URL 配置正确。\n  原因：{exc.orig}\n",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    with Session(engine) as session:
        bootstrap_modules(session)
        from app.modules.workflow.service.workflow_service import recover_orphaned_instances

        recover_orphaned_instances(session)
    print(f"{settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    yield
    # 关闭时执行：释放 checkpointer 持有的底层 DB 连接（sqlite3 / psycopg 单例）
    from app.modules.workflow.service.checkpointer import close_checkpointer

    close_checkpointer()
    print(f"{settings.APP_NAME} 已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Loom AI 内容生成平台 API",
    lifespan=lifespan,
)

register_exception_handlers(app)
api_router = create_api_router()
app.include_router(api_router)
if settings.API_VERSION_PREFIX_ENABLED:
    app.include_router(api_router, prefix=settings.API_VERSION_PREFIX.rstrip("/"))
UPLOADS_DIR = DEFAULT_UPLOAD_DIR
Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)

# 强制下载（不内联渲染）的扩展名：可执行/可内联内容须设 attachment，防浏览器自动渲染（如 PDF 内嵌 JS）
_UPLOAD_FORCE_DOWNLOAD_EXTENSIONS = {".pdf"}


def _sanitize_download_filename(name: str) -> str:
    """过滤下载文件名中的特殊字符，防 HTTP 头注入（双引号、CR、LF、反斜杠）。"""
    return re.sub(r'["\r\n\\]', "_", name)


def _require_upload_token(request: Request) -> str:
    """从 Authorization header 或 token query 参数提取下载令牌并返回。

    <img src="/uploads/..."> 等无法自定义请求头的场景可用 ?token=<download_token> 传递。
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    token = request.query_params.get("token")
    if token:
        return token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证信息")


@app.get("/uploads/{file_path:path}")
async def serve_upload(
    file_path: str,
    token: str = Depends(_require_upload_token),
    session: Session = Depends(get_session),
):
    """提供上传文件访问，需专用下载令牌鉴权 + 资源归属校验。

    支持通过 Authorization: Bearer <token> 或 ?token=<token> 传递下载令牌。
    所有响应附 X-Content-Type-Options: nosniff 防内容嗅探；
    可执行/可内联类型（如 PDF）设 Content-Disposition: attachment 防自动渲染。

    鉴权策略：
    - get_user_from_download_token 校验令牌签名/类型/token_version，并查 DB 确认用户存在且
      is_active（verify_download_token 的无 DB 高频路径不校验 is_active，被禁用用户在 TTL 内
      仍可访问，故 /uploads 改用查 DB 版本）。
    - 非超管用户须为该文件（MediaAsset）的创建者，防止 IDOR 越权下载他人资源。
    """
    # 鉴权：校验下载令牌 + 用户有效（含 is_active），失败抛 401
    current_user = get_user_from_download_token(session, token)

    # 防路径穿越：解析后须仍位于 UPLOADS_DIR 内
    uploads_root = str(UPLOADS_DIR)
    full_path = os.path.abspath(os.path.join(uploads_root, file_path))
    try:
        common = os.path.commonpath([uploads_root, full_path])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    if common != uploads_root or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # IDOR 防护：非超管须为资源归属者。本地存储 storage_url 形如 /uploads/<file_path>，
    # file_path 已通过 isfile 校验为真实文件（UUID 命名，不含 SQL LIKE 通配符 % _）。
    if not is_super_admin(session, current_user):
        owned = session.exec(
            select(MediaAsset).where(
                MediaAsset.storage_url.endswith("/" + file_path),
                MediaAsset.created_by == current_user.id,
                MediaAsset.delete_time.is_(None),
            )
        ).first()
        if owned is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该资源")

    # nosniff 全量；可执行/可内联类型强制下载，避免浏览器自动渲染（PDF 等）
    headers = {"X-Content-Type-Options": "nosniff"}
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _UPLOAD_FORCE_DOWNLOAD_EXTENSIONS:
        # 过滤 filename 中的特殊字符，防 HTTP 头注入（双引号、换行符、反斜杠）
        safe_name = _sanitize_download_filename(os.path.basename(full_path))
        headers["Content-Disposition"] = f'attachment; filename="{safe_name}"'

    return FileResponse(full_path, headers=headers)


app.state.scope_whitelists = load_scope_whitelists()
app.state.module_runtime = {
    item.name: {
        "label": item.label,
        "description": item.description,
        "scopes": list(item.scopes),
        "config_namespace": item.config_namespace,
        "config_values": item.config_values,
        "init_resources": [resource.__dict__ for resource in item.init_resources],
        "menu_manifest": [menu.__dict__ for menu in item.menu_manifest],
        "module_root": item.module_root,
    }
    for item in load_module_runtime_infos()
}
app.state.cool_module = {
    item.name: {
        "name": item.label,
        "description": item.description,
    }
    for item in load_module_runtime_infos()
}

# 全局中间件
for middleware in reversed(load_global_middlewares()):
    app.add_middleware(middleware)

for binding in reversed(load_module_middlewares()):
    app.add_middleware(
        PrefixScopedMiddleware,
        middleware_cls=binding.middleware,
        prefixes=binding.prefixes,
        module_name=binding.module,
    )

# CORS 配置
# 放在最后以确保它是最外层中间件，能处理所有请求（包括预检）和错误响应的 CORS 头
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """健康检查"""
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "celery": _check_celery_config(),
        "settings": _check_startup_settings(),
    }
    status_value = "healthy" if all(item["status"] in {"ok", "skipped"} for item in checks.values()) else "degraded"
    return {"status": status_value, "checks": checks}


@app.get("/metrics")
async def metrics():
    """Prometheus 文本指标（通过 METRICS_ENABLED 控制记录）。"""
    if not settings.METRICS_ENABLED:
        return PlainTextResponse("# metrics disabled\n", media_type="text/plain")
    return PlainTextResponse(render_metrics(), media_type="text/plain")


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
        return {"status": "skipped", "message": "redis unavailable, memory fallback active"}
    try:
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _check_celery_config() -> dict:
    if not settings.CELERY_BROKER_URL:
        return {"status": "skipped", "message": "broker not configured"}
    return {"status": "ok", "broker": settings.CELERY_BROKER_URL.split("://", 1)[0]}


def _check_startup_settings() -> dict:
    results = validate_startup_settings()
    errors = [item for item in results if item.level == "error"]
    warnings = [item for item in results if item.level == "warning"]
    if errors:
        return {"status": "error", "items": [item.__dict__ for item in results]}
    if warnings:
        return {"status": "degraded", "items": [item.__dict__ for item in results]}
    return {"status": "ok"}
