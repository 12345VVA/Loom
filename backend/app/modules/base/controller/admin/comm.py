"""
Base 模块通用后台接口
"""
from fastapi import Depends, File, UploadFile
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User, UserPersonRead, UserPersonUpdateRequest
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="base",
        resource="comm",
        scope="admin",
        service=AuthService,
        tags=("base", "comm"),
        actions=(),
    )
)
class BaseCommController(BaseController):
    @Get("/person", summary="获取当前用户个人信息", permission="base:comm:person", role_codes=("admin", "task_operator"))
    async def person(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> UserPersonRead:
        return AuthService(session).person(current_user)

    @Get("/permmenu", summary="获取权限与菜单", permission="base:comm:permmenu", role_codes=("admin", "task_operator"))
    async def permmenu(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return AuthService(session).permmenu(current_user)

    @Post("/personUpdate", summary="修改当前用户信息", permission="base:comm:person_update", role_codes=("admin", "task_operator"))
    async def person_update(
        self,
        payload: UserPersonUpdateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return AuthService(session).person_update(current_user, payload)

    @Post("/logout", summary="退出登录", permission="base:session:logout", role_codes=("admin", "task_operator"))
    async def logout(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        AuthService(session).logout(current_user)
        return {"success": True}

    @Get("/uploadMode", summary="文件上传模式", permission="base:comm:upload_mode", role_codes=("admin", "task_operator"))
    async def upload_mode(self) -> dict:
        return {"mode": "local", "type": "local"}

    @Get("/program", summary="编程语言", anonymous=True)
    async def program(self) -> str:
        return "Python"

    @Post("/upload", summary="文件上传")
    async def upload(
        self,
        file: UploadFile = File(...),
    ) -> str:
        from app.framework.storage import StorageService
        
        file_content = await file.read()
        path = StorageService.get_instance().upload(file_content, file.filename)
        return path


router = BaseCommController.router
