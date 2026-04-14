"""
Base 模块菜单控制器
"""
from fastapi import Depends, Request
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import (
    MenuCreateAutoRequest,
    MenuCreateRequest,
    MenuExportRequest,
    MenuImportRequest,
    MenuParseRequest,
    MenuParseResponse,
    MenuRead,
    MenuTreeItem,
    MenuUpdateRequest,
    User,
)
from app.modules.base.service.admin_service import MenuAdminService
from app.modules.base.service.eps_service import EpsService
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/menu",
        scope="admin",
        service=MenuAdminService,
        tags=("base", "menu"),
        name_prefix="菜单",
        code_prefix="base_sys_menu",
        list_response_model=MenuTreeItem,
        page_item_model=MenuRead,
        info_response_model=MenuRead,
        add_request_model=MenuCreateRequest | list[MenuCreateRequest],
        add_response_model=MenuRead | list[MenuRead],
        update_request_model=MenuUpdateRequest,
        update_response_model=MenuRead,
        list_query=QueryConfig(
            keyword_like_fields=("name", "code", "permission"),
            field_eq=(QueryFieldConfig("parent_id", "parentId"), QueryFieldConfig("is_active", "status"), "type"),
            field_like=("name", "code", "permission"),
            order_fields=("sort_order", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("sort_order", "asc"), OrderByConfig("created_at", "asc")),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name", "code", "permission"),
            field_eq=(QueryFieldConfig("parent_id", "parentId"), QueryFieldConfig("is_active", "status"), "type"),
            field_like=("name", "code", "permission"),
            order_fields=("sort_order", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("sort_order", "asc"), OrderByConfig("created_at", "asc")),
        ),
        is_tree=True,
        parent_field="parent_id",
        soft_delete=True,
    )
)
class BaseMenuController(BaseController):
    @Get(
        "/tree",
        summary="获取菜单树",
        permission="base:sys:menu:tree",
    )
    async def menu_tree(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[MenuTreeItem]:
        service = MenuAdminService(session)
        return service.tree()

    @Get(
        "/roleMenuIds",
        summary="获取角色菜单 ID 列表",
        permission="base:sys:menu:role_menu_ids",
    )
    async def role_menu_ids(
        self,
        role_id: int,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[int]:
        service = MenuAdminService(session)
        return service.role_menu_ids(role_id)

    @Get(
        "/currentTree",
        summary="获取当前用户菜单树",
        permission="base:sys:menu:current_tree",
        role_codes=("admin", "task_operator"),
    )
    async def current_tree(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[MenuTreeItem]:
        service = MenuAdminService(session)
        return service.current_tree(current_user)

    @Post(
        "/export",
        summary="导出菜单",
        permission="base:sys:menu:export",
    )
    async def export_menu(
        self,
        payload: MenuExportRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[dict]:
        service = MenuAdminService(session)
        return service.export(payload)

    @Post(
        "/import",
        summary="导入菜单",
        permission="base:sys:menu:import",
    )
    async def import_menu(
        self,
        payload: MenuImportRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = MenuAdminService(session)
        return service.import_menu(payload)

    @Post(
        "/parse",
        summary="解析菜单候选",
        permission="base:sys:menu:parse",
    )
    async def parse_menu(
        self,
        request: Request,
        payload: MenuParseRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> MenuParseResponse:
        eps = EpsService(request.app).export_admin()
        return MenuAdminService(session).parse_menu_candidates(payload, eps)

    @Post(
        "/create",
        summary="快速创建菜单",
        permission="base:sys:menu:create",
    )
    async def create_menu(
        self,
        payload: MenuCreateAutoRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[MenuRead]:
        service = MenuAdminService(session)
        return service.create_auto(payload)


router = BaseMenuController.router
