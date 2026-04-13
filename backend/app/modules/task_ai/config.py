"""
Task 模块配置
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="task_ai",
    label="AI 任务模块",
    description="AI 提示词处理与业务任务模块",
    order=4,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="TASK_AI",
    init_db_file="init_db.py",
    init_menu_file="menu.json",
)
