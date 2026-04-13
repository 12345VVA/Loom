"""
Loom API - FastAPI 主入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.framework.api.exception_handlers import register_exception_handlers
from app.framework.middleware.module_runtime import PrefixScopedMiddleware
from app.framework.router import create_api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.database import Session, engine
from app.modules import (
    bootstrap_modules,
    load_scope_whitelists,
    load_global_middlewares,
    load_module_middlewares,
    load_module_runtime_infos,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    init_db()
    with Session(engine) as session:
        bootstrap_modules(session)
    print(f"{settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    yield
    # 关闭时执行
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
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"status": "healthy"}
