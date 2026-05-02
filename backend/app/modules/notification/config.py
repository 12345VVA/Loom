"""
Notification 模块配置
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="notification",
    label="通知模块",
    description="站内通知、通知模板和受众规则",
    order=6,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="NOTIFICATION",
    init_menu_file="menu.json",
)
