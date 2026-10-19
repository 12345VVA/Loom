"""AI 治理告警发送入口（ai→notification 方向解耦，2026-10-18 批次2）。

ai 模块经 registry 回调 ``governance_alert`` 调用本函数（main.py 装配期注册），
不 import notification——告警标题/受众/落地页等通知侧呈现细节收敛在本模块，
ai 侧只透传业务语义（message/business_key/level）。
"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.notification.model.notification import AudienceRule
from app.modules.notification.service.notification_service import NotificationService

GOVERNANCE_ALERT_TITLE = "AI 治理告警"
GOVERNANCE_ALERT_LINK = "/ai/governance-event"


def send_governance_alert(
    session: Session,
    *,
    message: str,
    business_key: str,
    level: str,
) -> bool:
    """发送 AI 治理告警（全量管理员受众，business_key 幂等去重沿用 send_business）。

    返回是否发送成功；异常向上抛由调用方（ai 侧 _notify_once）兜底降级。
    """
    NotificationService(session).send_business(
        title=GOVERNANCE_ALERT_TITLE,
        content=message,
        audience=AudienceRule(all_admins=True),
        source_module="ai",
        business_key=business_key,
        level=level,
        link_url=GOVERNANCE_ALERT_LINK,
    )
    return True
