"""
工作流实例执行与监控 API 接口。
"""

import asyncio
import json
import logging

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow.model.workflow import (
    NodeTestRequest,
    NodeTestResponse,
    WorkflowExecutionLog,
    WorkflowExecutionLogRead,
    WorkflowInstance,
    WorkflowInstanceCancelRequest,
    WorkflowInstanceRead,
    WorkflowInstanceResumeRequest,
    WorkflowInstanceStartRequest,
)
from app.modules.workflow.service.workflow_service import (
    WorkflowInstanceService,
    assert_workflow_owner,
)

logger = logging.getLogger(__name__)


def _restore_logs_payload(logs: list[WorkflowExecutionLog]) -> None:
    """T8+T6 还原节点载荷：先按 storage_ref 回填对象存储内容，再用前一条 output 填充 ref_prev 的 input。

    前端拿到的 input_data/output_data 为还原后的完整脱敏载荷字符串，base-node 零改动。
    """
    from app.framework.storage import resolve_payload

    prev_output: str | None = None
    for log in logs:
        log.input_data = resolve_payload(log.input_data, log.input_storage_ref)
        log.output_data = resolve_payload(log.output_data, log.output_storage_ref)
        if getattr(log, "payload_type", "full") == "ref_prev":
            log.input_data = prev_output if prev_output is not None else "{}"
        prev_output = log.output_data


def _replace_transferred_urls(logs: list[WorkflowExecutionLog], instance_id: int, session: Session) -> None:
    """若工作流执行产物已成功转存到本地存储，将日志载荷中的远程原始 URL 替换为本地 storage_url，
    使前端日志抽屉与画廊优先展示并下载本地图片链接。
    """
    import re

    from sqlmodel import or_

    from app.modules.media.model.media import MediaAsset
    from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

    # 1. 扫描日志载荷中包含的所有 http/https 远程 URL
    url_pattern = re.compile(r'https?://[^\s"\'<>\\]+')
    found_urls: set[str] = set()
    for log in logs:
        if log.output_data:
            found_urls.update(url_pattern.findall(log.output_data))
        if log.input_data:
            found_urls.update(url_pattern.findall(log.input_data))

    conditions = [MediaAsset.workflow_instance_id == instance_id]
    if found_urls:
        conditions.append(MediaAsset.original_url.in_(list(found_urls)))

    assets = session.exec(
        select(MediaAsset).where(
            or_(*conditions),
            MediaAsset.status == "success",
            MediaAsset.delete_time == None,  # noqa: E711
        )
    ).all()
    url_map: dict[str, str] = {a.original_url: a.storage_url for a in assets if a.original_url and a.storage_url}

    art_conditions = [WorkflowArtifact.instance_id == instance_id]
    if found_urls:
        art_conditions.append(WorkflowArtifact.original_url.in_(list(found_urls)))

    artifacts = session.exec(
        select(WorkflowArtifact).where(
            or_(*art_conditions),
            WorkflowArtifact.storage_url != None,  # noqa: E711
            WorkflowArtifact.original_url != None,  # noqa: E711
        )
    ).all()
    for art in artifacts:
        if art.original_url and art.storage_url:
            url_map[art.original_url] = art.storage_url

    if not url_map:
        return

    for log in logs:
        if log.output_data:
            for orig, stor in url_map.items():
                if orig in log.output_data:
                    log.output_data = log.output_data.replace(orig, stor)
        if log.input_data:
            for orig, stor in url_map.items():
                if orig in log.input_data:
                    log.input_data = log.input_data.replace(orig, stor)


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
            field_eq=(
                "definition_id",
                "status",
                QueryFieldConfig(column="run_type", request_param="runType"),  # 运行类型分段过滤（默认 production）
            ),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class WorkflowInstanceController(BaseController):
    @Post("/start", summary="启动工作流实例", permission="workflow:instance:start")
    def start(
        self,
        payload: WorkflowInstanceStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = WorkflowInstanceService(session)
        instance = service.start_instance(payload.definition_id, payload.inputs, current_user)
        return {"id": instance.id}

    @Post("/trial", summary="试运行工作流（草稿版）", permission="workflow:instance:trial")
    def trial(
        self,
        payload: WorkflowInstanceStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """编辑器试运行：跑草稿版（draft_version_id），区别于 /start 跑已发布版。"""
        service = WorkflowInstanceService(session)
        instance = service.start_trial_instance(payload.definition_id, payload.inputs, current_user)
        return {"id": instance.id}

    @Post("/resume", summary="提供人工确认恢复执行", permission="workflow:instance:resume")
    def resume(
        self,
        payload: WorkflowInstanceResumeRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        service = WorkflowInstanceService(session)
        instance = service.resume_instance(payload.instance_id, payload.user_input, current_user)
        return instance

    @Post("/cancel", summary="取消运行中的工作流实例", permission="workflow:instance:cancel")
    def cancel(
        self,
        payload: WorkflowInstanceCancelRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        service = WorkflowInstanceService(session)
        instance = service.cancel_instance(payload.instance_id, current_user)
        return {"id": instance.id, "status": instance.status}

    @Post("/testNode", summary="单节点测试运行", permission="workflow:instance:testNode")
    async def test_node(
        self,
        payload: NodeTestRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> NodeTestResponse:
        service = WorkflowInstanceService(session)
        result = await service.test_node(payload.definition_id, payload.node_id, payload.mock_variables, current_user)
        return result

    @Get("/logs", summary="获取执行日志步骤列表", permission="workflow:instance:logs")
    def get_logs(
        self,
        instance_id: int = Query(..., alias="instanceId"),
        since_log_id: int | None = Query(None, alias="sinceLogId", description="仅返回 id 大于此值的日志（增量拉取）"),
        limit: int | None = Query(None, le=500, description="最多返回条数，缺省全量"),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[WorkflowExecutionLogRead]:
        instance = session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流实例不存在")
        assert_workflow_owner(session, instance, current_user)
        stmt = select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == instance_id)
        if since_log_id is not None:
            stmt = stmt.where(WorkflowExecutionLog.id > since_log_id)
        stmt = stmt.order_by(WorkflowExecutionLog.created_at.asc(), WorkflowExecutionLog.id.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        logs = session.exec(stmt).all()
        _restore_logs_payload(logs)
        _replace_transferred_urls(logs, instance_id, session)
        return logs

    @Get("/stream", summary="SSE 实时推送工作流进度", permission="workflow:instance:page")
    async def stream_progress(
        self,
        instance_id: int = Query(..., alias="instanceId"),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        """
        开启 SSE 长连接，通过 Redis pub/sub 实时推送节点状态迁移事件。
        无 Redis 时降级为心跳保活 + 进程内事件推送。
        """
        instance = session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流实例不存在")
        assert_workflow_owner(session, instance, current_user)
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

                    if event_name in ("success", "failed", "paused", "cancelled"):
                        break
            except asyncio.CancelledError:
                logger.info("工作流实例 %d 的 SSE 监控长连接已被客户端关闭", instance_id)

        # 反代理防缓冲三件套与 AI 侧 model.py 对齐：Nginx 默认 proxy_buffering on，
        # 缺 X-Accel-Buffering: no 时节点状态事件会攒到缓冲满才刷出（prod compose 拓扑必现）
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


router = WorkflowInstanceController.router
