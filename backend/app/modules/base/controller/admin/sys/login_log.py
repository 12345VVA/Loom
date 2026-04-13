"""
登录日志接口
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.modules.base.model.sys import SysLoginLogCreateRequest, SysLoginLogRead, SysLoginLogUpdateRequest
from app.modules.base.service.sys_manage_service import SysLoginLogService


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/login_log",
        scope="admin",
        service=SysLoginLogService,
        tags=("base", "sys", "login_log"),
        list_response_model=SysLoginLogRead,
        page_item_model=SysLoginLogRead,
        info_response_model=SysLoginLogRead,
        add_request_model=SysLoginLogCreateRequest,
        add_response_model=SysLoginLogRead,
        update_request_model=SysLoginLogUpdateRequest,
        update_response_model=SysLoginLogRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        list_query=QueryConfig(
            keyword_like_fields=("name", "account", "ip", "device_id"),
            field_eq=(
                QueryFieldConfig("login_type", "loginType"),
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("risk_hit", "riskHit"),
            ),
            field_like=("name", "account", "ip", "device_id"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name", "account", "ip", "device_id"),
            field_eq=(
                QueryFieldConfig("login_type", "loginType"),
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("risk_hit", "riskHit"),
            ),
            field_like=("name", "account", "ip", "device_id"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class BaseSysLoginLogController(BaseController):
    pass


router = BaseSysLoginLogController.router
