"""
系统日志接口
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.model.sys import SysLogKeepRequest, SysLogRead
from app.modules.base.service.security_service import get_current_user
from app.modules.base.service.sys_manage_service import SysLogService


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/log",
        scope="admin",
        service=SysLogService,
        tags=("base", "sys", "log"),
        page_item_model=SysLogRead,
        info_response_model=SysLogRead,
        actions=("page",),
        page_query=QueryConfig(
            keyword_like_fields=("action", "ip", "message"),
            field_like=("action", "ip", "message"),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class BaseSysLogController(BaseController):
    @Post("/clear", summary="清理", permission="base:sys:log:clear")
    async def clear(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return SysLogService(session).clear()

    @Post("/setKeep", summary="日志保存时间", permission="base:sys:log:setKeep")
    async def set_keep(
        self,
        payload: SysLogKeepRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return SysLogService(session).set_keep(payload.model_dump())

    @Get("/getKeep", summary="获得日志保存时间", permission="base:sys:log:getKeep")
    async def get_keep(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> str:
        return SysLogService(session).get_keep()


router = BaseSysLogController.router
