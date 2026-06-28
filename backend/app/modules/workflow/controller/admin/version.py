"""工作流版本管理 API：版本历史 + 发布/回滚/对比。

版本表 workflow_definition_version 的自动 page/info/list 经 DataScope 过滤
（版本表冗余 user_id = definition owner）。page 按 definitionId/status 过滤。
"""

from fastapi import Depends, Query
from sqlmodel import Session

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
from app.modules.workflow.model.workflow_version import (
    WorkflowDefinitionVersionDetailRead,
    WorkflowDefinitionVersionRead,
    WorkflowPublishRequest,
    WorkflowRollbackRequest,
)
from app.modules.workflow.service.workflow_version_service import WorkflowVersionService


@CoolController(
    CoolControllerMeta(
        module="workflow",
        resource="version",
        scope="admin",
        service=WorkflowVersionService,
        tags=("workflow", "version"),
        code_prefix="workflow_version",
        list_response_model=WorkflowDefinitionVersionRead,
        page_item_model=WorkflowDefinitionVersionRead,
        info_response_model=WorkflowDefinitionVersionDetailRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            field_eq=(
                QueryFieldConfig(column="definition_id", request_param="definitionId"),
                QueryFieldConfig(column="status", request_param="status"),
            ),
            order_fields=("created_at", "version_no"),
            add_order_by=(OrderByConfig("version_no", "desc"),),
        ),
        soft_delete=False,  # 版本不软删除，归档走 status=archived
    )
)
class WorkflowVersionController(BaseController):
    @Post("/publish", summary="发布草稿", permission="workflow:version:publish")
    def publish(
        self,
        payload: WorkflowPublishRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """草稿→发布（一步上线）。正在运行的实例按其 version_id 继续跑旧版，不受影响。"""
        version = WorkflowVersionService(session).publish(
            payload.definition_id, payload.change_note, current_user
        )
        return WorkflowDefinitionVersionRead.model_validate(version).model_dump(by_alias=True)

    @Post("/rollback", summary="回滚到历史版本", permission="workflow:version:rollback")
    def rollback(
        self,
        payload: WorkflowRollbackRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """回滚：默认把目标版本复制为新草稿（确认后再发布）；immediate=true 直接上线。"""
        return WorkflowVersionService(session).rollback(
            payload.definition_id,
            payload.target_version_id,
            payload.change_note,
            current_user,
            immediate=payload.immediate,
        )

    @Get("/diff", summary="两版本结构对比", permission="workflow:version:diff")
    def diff(
        self,
        versionA: int = Query(..., alias="versionA"),
        versionB: int = Query(..., alias="versionB"),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return WorkflowVersionService(session).diff(versionA, versionB, current_user)


router = WorkflowVersionController.router
