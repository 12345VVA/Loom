"""
系统定时任务接口
"""
from fastapi import Depends, Request
from sqlmodel import Session
from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, CrudQuery, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Get, Post
from app.modules.task.model.task import TaskInfoCreateRequest, TaskInfoRead, TaskInfoUpdateRequest
from app.modules.task.service.task_service import TaskInfoService

@CoolController(
    CoolControllerMeta(
        module="task",
        resource="info",
        scope="admin",
        service=TaskInfoService,
        tags=("task", "info"),
        code_prefix="task_info",
        list_response_model=TaskInfoRead,
        page_item_model=TaskInfoRead,
        info_response_model=TaskInfoRead,
        add_request_model=TaskInfoCreateRequest,
        add_response_model=TaskInfoRead,
        update_request_model=TaskInfoUpdateRequest,
        update_response_model=TaskInfoRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("name",),
            field_eq=("status", "type", QueryFieldConfig("task_type", "taskType")),
            field_like=("name",),
            order_fields=("created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class TaskInfoController(BaseController):
    @Get("/log", summary="任务日志", permission="task:info:log")
    async def log(
        self,
        request: Request,
        session: Session = Depends(get_session),
    ):
        query = CrudQuery.from_request(request)
        return TaskInfoService(session).log(query)

    @Post("/start", summary="开始任务", permission="task:info:start")
    async def start(
        self,
        payload: dict,
        session: Session = Depends(get_session),
    ):
        task_id = payload.get("id")
        return await TaskInfoService(session).start(task_id)

    @Post("/stop", summary="停止任务", permission="task:info:stop")
    async def stop(
        self,
        payload: dict,
        session: Session = Depends(get_session),
    ):
        task_id = payload.get("id")
        return await TaskInfoService(session).stop(task_id)

    @Post("/once", summary="立即执行一次", permission="task:info:once")
    async def once(
        self,
        payload: dict,
        session: Session = Depends(get_session),
    ):
        task_id = payload.get("id")
        return await TaskInfoService(session).once(task_id)

router = TaskInfoController.router
