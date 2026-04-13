"""
Task 模块管理端接口
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    BeforeHookConfig,
    CoolController,
    CoolControllerMeta,
    InsertParamConfig,
    OrderByConfig,
    QueryConfig,
    ServiceApiConfig,
)
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.task_ai.model.task import (
    TaskCancelRequest,
    TaskCreate,
    TaskDeleteRequest,
    TaskRead,
    TaskUpdate,
)
from app.modules.task_ai.service.task_service import TaskService


@CoolController(
    CoolControllerMeta(
        module="task_ai",
        resource="info",
        scope="admin",
        service=TaskService,
        tags=("task_ai",),
        name_prefix="AI任务",
        code_prefix="task_ai_info",
        role_codes=("admin", "task_operator"),
        list_response_model=TaskRead,
        page_item_model=TaskRead,
        info_response_model=TaskRead,
        info_param_type=str,
        add_request_model=TaskCreate,
        add_response_model=TaskRead,
        update_request_model=TaskUpdate,
        update_response_model=TaskRead,
        delete_request_model=TaskDeleteRequest,
        before_hooks=(
            BeforeHookConfig(action="add", method="normalize_payload"),
            BeforeHookConfig(action="update", method="normalize_payload"),
        ),
        insert_params=(
            InsertParamConfig(action="add", target="payload.user_id", source="current_user.id"),
        ),
        list_query=QueryConfig(
            keyword_like_fields=("prompt",),
            field_eq=("status", "task_type", "user_id"),
            field_like=("prompt",),
            order_fields=("created_at", "updated_at", "progress", "status"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("prompt",),
            field_eq=("status", "task_type", "user_id"),
            field_like=("prompt",),
            order_fields=("created_at", "updated_at", "progress", "status"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        service_apis=(
            ServiceApiConfig(
                method="stats",
                summary="获取任务统计",
                permission="task_ai:info:stats",
                role_codes=("admin", "task_operator"),
            ),
        ),
    )
)
class TaskAdminController(BaseController):
    @Post(
        "/cancel",
        summary="取消任务",
        permission="task_ai:info:cancel",
        role_codes=("admin", "task_operator"),
    )
    async def cancel(
        self,
        payload: TaskCancelRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = TaskService(session)
        return service.cancel(payload, current_user=current_user)


router = TaskAdminController.router
