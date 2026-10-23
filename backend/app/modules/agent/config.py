"""智能体模块配置。"""

from sqlmodel import Session

from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="agent",
    label="智能体",
    description="LangGraph 智能体运行时（SPI 工具注册 + 发布快照 + 会话观测）",
    order=11,
    scopes=("admin",),
    config_namespace="AGENT",
    init_menu_file="menu.json",
    # bootstrap（SPI 工具收集，P2 接入）：收集失败标记 degraded，不阻断全站启动
    bootstrap="app.modules.agent.config.bootstrap",
)


def bootstrap(session: Session) -> None:
    """应用启动时收集各业务模块 agent_tools（评审 11：启动期暴露结构/冲突错误）。

    P2 落地收集器；当前为占位（不收集不报错）。
    """
    return None
