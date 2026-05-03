"""
媒体资源模块配置。
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig


MODULE_CONFIG = ModuleConfig(
    name="media",
    label="媒体资源",
    description="AI 生成产物与人工上传素材资源库",
    order=8,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="MEDIA",
    init_menu_file="menu.json",
)
