"""
工作流可视化管理与运行时模块配置。
"""

import logging

from sqlmodel import Session, select

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

logger = logging.getLogger(__name__)

MODULE_CONFIG = ModuleConfig(
    name="workflow",
    label="工作流管理",
    description="可视化 Agent 工作流，集成 LangGraph 运行时",
    order=8,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="WORKFLOW",
    bootstrap="app.modules.workflow.config.bootstrap",
    init_menu_file="menu.json",
)


def bootstrap(session: Session) -> None:
    """模块启动初始化：幂等注册工作流通知模板。"""
    from app.modules.notification.model.notification import NotificationTemplate

    code = "workflow.failed"
    existing = session.exec(select(NotificationTemplate).where(NotificationTemplate.code == code)).first()
    if existing:
        return
    template = NotificationTemplate(
        code=code,
        name="工作流执行失败",
        title_template="工作流「{workflow_name}」执行失败",
        content_template="实例 #{instance_id} 在节点 {node_id} 失败：{error_message}",
        default_level="error",
        is_active=True,
    )
    session.add(template)
    session.commit()
    logger.info("已初始化通知模板 %s", code)
