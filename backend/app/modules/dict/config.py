"""
Dict 模块配置
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="dict",
    label="字典模块",
    description="字典管理模块",
    order=8,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="DICT",
    init_db_file="init_db.py",
    init_menu_file="menu.json",
    admin_whitelist=(
        "/admin/dict/info/types",
    ),
)
