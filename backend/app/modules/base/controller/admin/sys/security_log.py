"""
安全审计日志接口
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.modules.base.model.sys import SysSecurityLogRead, SysSecurityLogCreateRequest
from app.modules.base.service.sys_manage_service import SysSecurityLogService


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/security_log",
        scope="admin",
        service=SysSecurityLogService,
        tags=("base", "sys", "security_log"),
        list_response_model=SysSecurityLogRead,
        page_item_model=SysSecurityLogRead,
        info_response_model=SysSecurityLogRead,
        actions=("list", "page", "info"),  # 只读操作，不允许添加/修改/删除审计日志
        list_query=QueryConfig(
            keyword_like_fields=("operator_name", "target_name", "remark"),
            field_eq=(
                QueryFieldConfig("operator_id", "operatorId"),
                QueryFieldConfig("target_type", "targetType"),
                QueryFieldConfig("operation", "operation"),
                QueryFieldConfig("module", "module"),
                QueryFieldConfig("status", "status"),
            ),
            field_like=("operator_name", "target_name", "remark"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("operator_name", "target_name", "remark"),
            field_eq=(
                QueryFieldConfig("operator_id", "operatorId"),
                QueryFieldConfig("target_type", "targetType"),
                QueryFieldConfig("operation", "operation"),
                QueryFieldConfig("module", "module"),
                QueryFieldConfig("status", "status"),
            ),
            field_like=("operator_name", "target_name", "remark"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class BaseSysSecurityLogController(BaseController):
    pass


router = BaseSysSecurityLogController.router
