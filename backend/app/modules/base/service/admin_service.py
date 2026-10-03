"""
Base 模块管理服务（门面）。

实现按资源域拆分：
- admin_base.py — payload 兼容/实体 diff 工具 + BaseAdminCrudService 基类
- user_admin_service.py / role_admin_service.py / department_admin_service.py / menu_admin_service.py

本模块保留全部历史符号的 re-export，外部统一从 `app.modules.base.service.admin_service` 引用。
"""

from app.modules.base.service.admin_base import (
    BaseAdminCrudService,
    compute_entity_diff,
    entity_to_dict,
    get_payload_attr,
    get_request_ip_from_payload,
    get_request_ip_from_request,
    has_payload_attr,
)
from app.modules.base.service.department_admin_service import DepartmentAdminService
from app.modules.base.service.menu_admin_service import MenuAdminService
from app.modules.base.service.role_admin_service import RoleAdminService
from app.modules.base.service.user_admin_service import UserAdminService

__all__ = [
    "BaseAdminCrudService",
    "DepartmentAdminService",
    "MenuAdminService",
    "RoleAdminService",
    "UserAdminService",
    "compute_entity_diff",
    "entity_to_dict",
    "get_payload_attr",
    "get_request_ip_from_payload",
    "get_request_ip_from_request",
    "has_payload_attr",
]
