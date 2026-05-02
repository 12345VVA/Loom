"""
AI 模型管理模块配置。
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig


MODULE_CONFIG = ModuleConfig(
    name="ai",
    label="AI 模型管理",
    description="AI 厂商、模型、调用配置与统一运行时",
    order=7,
    scopes=("admin", "aiapi"),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="AI",
    init_menu_file="menu.json",
)
