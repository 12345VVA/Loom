"""
Base 模块用户控制器
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.modules.base.model.auth import (
    CoolUserInfo,
    Department,
    PageResult,
    User,
    UserListItem,
    UserInfoItem,
    UserCreateRequest,
    UserUpdateRequest,
    UserRoleAssignRequest,
    UserMoveRequest,
)
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
    RelationConfig,
)
from app.modules.base.service.admin_service import UserAdminService
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.security_service import get_current_user
from app.framework.router.route_meta import Get, Post


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        tags=("base", "user"),
        name_prefix="用户",
        code_prefix="base_sys_user",
        list_response_model=UserListItem,
        page_item_model=UserListItem,
        info_response_model=UserInfoItem,
        add_request_model=UserCreateRequest,
        add_response_model=UserListItem,
        update_request_model=UserUpdateRequest,
        update_response_model=UserListItem,
        info_ignore_property=("password_version",),
        list_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email", "phone", "nick_name"),
            field_eq=(QueryFieldConfig("department_id", "departmentIds"), QueryFieldConfig("is_active", "status")),
            field_like=("username", "full_name", "nick_name", "email", "phone"),
            select=("id", "username", "full_name", "nick_name", "head_img", "email", "phone", "remark", "department_id", "is_active", "created_at", "updated_at"),
            order_fields=("created_at", "updated_at", "username"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email", "phone", "nick_name"),
            field_eq=(QueryFieldConfig("department_id", "departmentIds"), QueryFieldConfig("is_active", "status")),
            field_like=("username", "full_name", "nick_name", "email", "phone"),
            select=("id", "username", "full_name", "nick_name", "head_img", "email", "phone", "remark", "department_id", "is_active", "created_at", "updated_at"),
            order_fields=("created_at", "updated_at", "username"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
        relations=(
            RelationConfig(
                model=Department,
                column="department_id",
                target_column="name",
                alias="departmentName"
            ),
        )
    )
)
class BaseUserController(BaseController):
    @Get(
        "/me",
        summary="获取当前登录用户信息",
        permission="base:sys:user:me",
        role_codes=("admin", "task_operator"),
    )
    async def get_me(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> CoolUserInfo:
        service = AuthService(session)
        return service.get_current_profile(current_user)

    @Post(
        "/assignRoles",
        summary="分配用户角色",
        permission="base:sys:user:assign_roles",
    )
    async def assign_roles(
        self,
        payload: UserRoleAssignRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> UserListItem:
        service = UserAdminService(session)
        return service.assign_roles(payload)

    @Post(
        "/move",
        summary="移动部门",
        permission="base:sys:user:move",
    )
    async def move(
        self,
        payload: UserMoveRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = UserAdminService(session)
        return service.move(payload)


router = BaseUserController.router
