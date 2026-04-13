"""
Base 模块角色控制器
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import RoleCreateRequest, RoleMenuAssignRequest, RoleRead, RoleUpdateRequest, User
from app.modules.base.service.admin_service import RoleAdminService
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/role",
        scope="admin",
        service=RoleAdminService,
        tags=("base", "role"),
        name_prefix="角色",
        code_prefix="base_sys_role",
        list_response_model=RoleRead,
        page_item_model=RoleRead,
        info_response_model=RoleRead,
        add_request_model=RoleCreateRequest,
        add_response_model=RoleRead,
        update_request_model=RoleUpdateRequest,
        update_response_model=RoleRead,
        list_query=QueryConfig(
            keyword_like_fields=("name", "code", "label", "remark"),
            field_eq=("is_active",),
            field_like=("name", "code", "label", "remark"),
            order_fields=("created_at", "updated_at", "name", "code"),
            add_order_by=(OrderByConfig("created_at", "asc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name", "code", "label", "remark"),
            field_eq=("is_active",),
            field_like=("name", "code", "label", "remark"),
            order_fields=("created_at", "updated_at", "name", "code"),
            add_order_by=(OrderByConfig("created_at", "asc"),),
        ),
    )
)
class BaseRoleController(BaseController):
    @Post(
        "/assignMenus",
        summary="分配角色菜单",
        permission="base:sys:role:assign_menus",
    )
    async def assign_menus(
        self,
        payload: RoleMenuAssignRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = RoleAdminService(session)
        return service.assign_menus(payload)


router = BaseRoleController.router
