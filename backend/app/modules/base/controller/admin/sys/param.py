"""
参数配置接口
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Get
from app.modules.base.model.sys import SysParamCreateRequest, SysParamRead, SysParamUpdateRequest
from app.modules.base.service.security_service import get_current_user
from app.modules.base.service.sys_manage_service import SysParamService
from app.modules.base.model.auth import User


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/param",
        scope="admin",
        service=SysParamService,
        tags=("base", "sys", "param"),
        list_response_model=SysParamRead,
        page_item_model=SysParamRead,
        info_response_model=SysParamRead,
        add_request_model=SysParamCreateRequest,
        add_response_model=SysParamRead,
        update_request_model=SysParamUpdateRequest,
        update_response_model=SysParamRead,
        actions=("add", "delete", "update", "page", "info"),
        list_query=QueryConfig(
            keyword_like_fields=("name", "key_name"),
            field_eq=(QueryFieldConfig("data_type", "dataType"),),
            field_like=("name", "key_name"),
            order_fields=("created_at", "updated_at", "name", "key_name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name", "key_name"),
            field_eq=(QueryFieldConfig("data_type", "dataType"),),
            field_like=("name", "key_name"),
            order_fields=("created_at", "updated_at", "name", "key_name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class BaseSysParamController(BaseController):
    @Get("/html", summary="获得网页内容的参数值", permission="base:sys:param:html")
    async def html_by_key(
        self,
        key: str,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> str:
        return SysParamService(session).html_by_key(key)


router = BaseSysParamController.router
