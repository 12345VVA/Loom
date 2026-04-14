"""
Base 模块部门控制器
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import (
    DepartmentDeleteRequest,
    DepartmentOrderItem,
    DepartmentRead,
    DepartmentUpdateRequest,
    DepartmentCreateRequest,
    User,
)
from app.modules.base.service.admin_service import DepartmentAdminService
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/department",
        scope="admin",
        service=DepartmentAdminService,
        tags=("base", "department"),
        name_prefix="部门",
        code_prefix="base_sys_department",
        list_response_model=DepartmentRead,
        page_item_model=DepartmentRead,
        info_response_model=DepartmentRead,
        add_request_model=DepartmentCreateRequest,
        add_response_model=DepartmentRead,
        update_request_model=DepartmentUpdateRequest,
        update_response_model=DepartmentRead,
        delete_request_model=DepartmentDeleteRequest,
        list_query=QueryConfig(
            keyword_like_fields=("name",),
            field_eq=(QueryFieldConfig("parent_id", "parentId"), QueryFieldConfig("is_active", "status")),
            field_like=("name",),
            order_fields=("sort_order", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("sort_order", "asc"), OrderByConfig("created_at", "asc")),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name",),
            field_eq=(QueryFieldConfig("parent_id", "parentId"), QueryFieldConfig("is_active", "status")),
            field_like=("name",),
            order_fields=("sort_order", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("sort_order", "asc"), OrderByConfig("created_at", "asc")),
        ),
        is_tree=True,
        parent_field="parent_id",
        soft_delete=True,
    )
)
class BaseDepartmentController(BaseController):
    @Post(
        "/order",
        summary="部门排序",
        permission="base:sys:department:order",
    )
    async def order(
        self,
        payload: list[DepartmentOrderItem],
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return DepartmentAdminService(session).order(payload)


router = BaseDepartmentController.router
