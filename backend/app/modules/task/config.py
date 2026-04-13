"""
Task 模块配置 (系统定时任务)
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="task",
    label="任务管理",
    description="系统定时任务调度模块",
    order=5,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="TASK",
)
