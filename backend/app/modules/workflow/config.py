"""
工作流可视化管理与运行时模块配置。
"""
from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig


MODULE_CONFIG = ModuleConfig(
    name="workflow",
    label="工作流管理",
    description="可视化 Agent 工作流，集成 LangGraph 运行时",
    order=8,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="WORKFLOW",
    init_menu_file="menu.json",
)
