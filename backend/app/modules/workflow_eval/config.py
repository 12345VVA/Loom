"""工作流评价系统模块配置。"""

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="workflow_eval",
    label="工作流评估",
    description="工作流测试集管理与批量评估：质量评分、P95 延迟、token/成本汇总、版本回归对比",
    order=9,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="WORKFLOW_EVAL",
    init_menu_file="menu.json",
)
