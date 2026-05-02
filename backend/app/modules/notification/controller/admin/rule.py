"""
通知规则接口。
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.modules.notification.model.notification import (
    NotificationRuleCreateRequest,
    NotificationRuleRead,
    NotificationRuleUpdateRequest,
)
from app.modules.notification.service.notification_service import NotificationRuleService


@CoolController(
    CoolControllerMeta(
        module="notification",
        resource="rule",
        scope="admin",
        service=NotificationRuleService,
        tags=("notification", "rule"),
        code_prefix="notification_rule",
        list_response_model=NotificationRuleRead,
        page_item_model=NotificationRuleRead,
        info_response_model=NotificationRuleRead,
        add_request_model=NotificationRuleCreateRequest,
        add_response_model=NotificationRuleRead,
        update_request_model=NotificationRuleUpdateRequest,
        update_response_model=NotificationRuleRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name"),
            field_eq=("is_active", "all_admins", "condition"),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "code", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class NotificationRuleController(BaseController):
    pass


router = NotificationRuleController.router
