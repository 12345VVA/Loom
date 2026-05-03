"""
AI 生成任务管理接口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiGenerationTaskRead, AiTaskActionRequest, AiTaskSubmitRequest
from app.modules.ai.service.ai_service import AiGenerationTaskService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="task",
        scope="admin",
        service=AiGenerationTaskService,
        tags=("ai", "task"),
        code_prefix="ai_task",
        list_response_model=AiGenerationTaskRead,
        page_item_model=AiGenerationTaskRead,
        info_response_model=AiGenerationTaskRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("task_type", "scenario", "profile_code", "status", "error_message"),
            field_eq=("task_type", "scenario", "profile_code", "status", "created_by"),
            field_like=("scenario", "profile_code", "error_message"),
            order_fields=("created_at", "updated_at", "started_at", "finished_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        list_query=QueryConfig(
            keyword_like_fields=("task_type", "scenario", "profile_code", "status", "error_message"),
            field_eq=("task_type", "scenario", "profile_code", "status", "created_by"),
            field_like=("scenario", "profile_code", "error_message"),
            order_fields=("created_at", "updated_at", "started_at", "finished_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AiGenerationTaskController(BaseController):
    @Post("/submit", summary="提交 AI 生成任务", permission="ai:task:submit")
    async def submit(
        self,
        payload: AiTaskSubmitRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGenerationTaskService(session).submit(payload, current_user)

    @Post("/cancel", summary="取消 AI 生成任务", permission="ai:task:cancel")
    async def cancel(
        self,
        payload: AiTaskActionRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGenerationTaskService(session).cancel(payload.id)

    @Post("/retry", summary="重试 AI 生成任务", permission="ai:task:retry")
    async def retry(
        self,
        payload: AiTaskActionRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGenerationTaskService(session).retry(payload.id)

    @Post("/stats", summary="AI 生成任务统计", permission="ai:task:stats")
    async def stats(
        self,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiGenerationTaskService(session).stats()


router = AiGenerationTaskController.router
