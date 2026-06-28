"""工作流评估人工标注模块配置。"""

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="workflow_annotation",
    label="评估标注",
    description="评估用例结果的人工标注与 LLM judge 校准（Cohen's κ 一致性）",
    order=10,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="WORKFLOW_ANNOTATION",
    init_menu_file="menu.json",
)
