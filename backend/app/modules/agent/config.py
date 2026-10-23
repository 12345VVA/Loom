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
    # bootstrap（SPI 工具收集，评审 11）：启动期暴露结构/冲突错误；失败 degraded 不阻断全站
    bootstrap="app.modules.agent.config.bootstrap",
)


def bootstrap(session: Session) -> None:
    """应用启动时收集各业务模块 agent_tools（build-then-swap）+ 资源层同步。

    失败处理区分两情形（评审 v1.4）：
    - 启动收集失败 = 无任何可信注册表 → Agent 功能 degraded（run 拒绝执行，tool.list 显示）；
    - 资源层 sync 失败 = 已有有效执行注册表 → 可重试（refresh 端点），不影响工具执行。
    """
    import logging

    from app.modules.agent.service import tool_registry

    logger = logging.getLogger("agent.bootstrap")
    tool_registry.bootstrap_registry()
    try:
        result = tool_registry.sync_resources(session)
        logger.info("agent 工具资源层同步完成：%s", result["count"])
    except Exception as exc:  # noqa: BLE001 —— 资源同步失败可重试，不阻断启动
        logger.warning("agent 工具资源层同步失败（可经 tool/refresh 重试）：%s", exc)
