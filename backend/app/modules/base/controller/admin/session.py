"""
Base 模块设备会话管理接口

提供当前用户的活跃会话列表与远程踢出能力（仅管理自己的设备，参考谷歌账户设备活动）。
会话数据由 AuthService + authority_service 的 session 存储层维护（Redis，按 sid 独立）。
"""

from fastapi import Depends, Request
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import RevokeDeviceRequest, User
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="session",
        scope="admin",
        service=AuthService,
        tags=("base", "session"),
        actions=(),
    )
)
class BaseSessionController(BaseController):
    @Get("/list", summary="当前用户设备列表", role_codes=("admin", "task_operator"))
    def list(
        self,
        request: Request,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """返回当前用户全部活跃设备（按 device_id 聚合），标记当前设备 current=True。"""
        devices = AuthService(session).list_sessions(current_user, request)
        return {"list": devices, "total": len(devices)}

    @Post("/revoke", summary="踢出指定设备", role_codes=("admin", "task_operator"))
    def revoke(
        self,
        payload: RevokeDeviceRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """踢出当前用户的指定设备（deviceId 必须属于本人，会踢该设备全部会话）。"""
        AuthService(session).revoke_device(current_user, payload.device_id)
        return {"success": True}


router = BaseSessionController.router
