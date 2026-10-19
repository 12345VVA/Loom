"""
AI 模型管理模块配置。
"""

import logging

from sqlmodel import Session, select

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

logger = logging.getLogger(__name__)

MODULE_CONFIG = ModuleConfig(
    name="ai",
    label="AI 模型管理",
    description="AI 厂商、模型、调用配置与统一运行时",
    order=7,
    scopes=("admin", "aiapi"),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="AI",
    bootstrap="app.modules.ai.config.bootstrap",
    init_menu_file="menu.json",
)


def bootstrap(session: Session) -> None:
    """模块启动初始化：幂等种入默认全局治理规则（AI-027，出厂零治理种子的补齐）。

    observe 模式只记 breach 事件不阻断调用，阈值给宽松观测基线；
    运维确认用量形态后按需改 enforce 收紧或调整阈值。
    """
    from app.modules.ai.model.ai import AiGovernanceRule
    from app.modules.ai.service.utils import statement_including_deleted

    code = "default-global-daily"
    # 存在性检查含软删行：code 列库层 unique，软删行仍占用编码——不变量过滤软删行后
    # 误判「不存在」再插入会撞唯一键（MODULE_LOAD_STRICT 默认 True 时直接炸启动）
    existing = session.exec(
        statement_including_deleted(select(AiGovernanceRule).where(AiGovernanceRule.code == code))
    ).first()
    if existing:
        if existing.delete_time is not None:
            # 软删行占用唯一键，无法重建同 code 新行，唯一出路是复活种子规则
            existing.delete_time = None
            session.add(existing)
            session.commit()
            logger.info("默认全局治理规则 %s 曾被软删，已随启动恢复", code)
        return
    rule = AiGovernanceRule(
        code=code,
        name="默认全局日用量观测",
        scope_type="global",
        period="day",
        max_requests=50_000,
        max_tokens=100_000_000,
        max_cost_micro_usd=100_000_000,  # $100/日
        mode="observe",
        notify_enabled=False,  # 告警回调未装配时静默降级，默认不开免噪声
        is_active=True,
    )
    session.add(rule)
    session.commit()
    logger.info("已初始化默认全局治理规则 %s（observe 模式）", code)
