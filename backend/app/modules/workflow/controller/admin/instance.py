"""
工作流实例执行与监控 API 接口。
"""
import asyncio
import json
import logging
from typing import Any

from fastapi import Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
)
from app.framework.router.route_meta import Post, Get
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow.model.workflow import (
    WorkflowInstanceRead,
    WorkflowInstanceStartRequest,
    WorkflowInstanceResumeRequest,
    WorkflowExecutionLog,
    WorkflowExecutionLogRead,
)
from app.modules.workflow.service.workflow_service import WorkflowService, WorkflowInstanceService

logger = logging.getLogger(__name__)


@CoolController(
    CoolControllerMeta(
        module="workflow",
        resource="instance",
        scope="admin",
        service=WorkflowInstanceService,
        tags=("workflow", "instance"),
        code_prefix="workflow_instance",
        list_response_model=WorkflowInstanceRead,
        page_item_model=WorkflowInstanceRead,
        info_response_model=WorkflowInstanceRead,
        actions=("page", "info", "list", "delete"),
        page_query=QueryConfig(
            keyword_like_fields=("status", "current_node"),
            field_eq=("definition_id", "status"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class WorkflowInstanceController(BaseController):

    @Post("/start", summary="启动工作流实例", permission="workflow:instance:start")
    async def start(
        self,
        payload: WorkflowInstanceStartRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = WorkflowInstanceService(session)
        instance = await service.start_instance(payload.definition_id, payload.inputs)
        return {"id": instance.id}

    @Post("/resume", summary="提供人工确认恢复执行", permission="workflow:instance:resume")
    async def resume(
        self,
        payload: WorkflowInstanceResumeRequest,
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        service = WorkflowInstanceService(session)
        instance = await service.resume_instance(payload.instance_id, payload.user_input)
        return instance

    @Get("/logs", summary="获取执行日志步骤列表", permission="workflow:instance:logs")
    async def get_logs(
        self,
        instance_id: int = Query(..., alias="instanceId"),
        _: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[WorkflowExecutionLogRead]:
        stmt = select(WorkflowExecutionLog).where(
            WorkflowExecutionLog.instance_id == instance_id
        ).order_by(WorkflowExecutionLog.created_at.asc())
        logs = session.exec(stmt).all()
        return logs

    @Get("/stream", summary="SSE 实时推送工作流进度", permission="workflow:instance:page")
    async def stream_progress(
        self,
        instance_id: int = Query(..., alias="instanceId"),
        _: User = Depends(get_current_user),
    ):
        """
        开启 SSE 长连接，通过 Redis pub/sub 实时推送节点状态迁移事件。
        无 Redis 时降级为心跳保活 + 进程内事件推送。
        """
        from app.modules.workflow.service.event_bus import subscribe_events

        async def event_generator():
            try:
                yield f"event: connect\ndata: {json.dumps({'status': 'connected'})}\n\n"

                async for event in subscribe_events(instance_id):
                    if event is None:
                        yield ": heartbeat\n\n"
                        continue

                    event_name = event["event_type"]
                    event_data = event["data"]

                    yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    if event_name in ("success", "failed", "paused"):
                        break
            except asyncio.CancelledError:
                logger.info("工作流实例 %d 的 SSE 监控长连接已被客户端关闭", instance_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream")


router = WorkflowInstanceController.router
