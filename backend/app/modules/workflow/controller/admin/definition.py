"""
工作流定义管理 API 接口。
"""

from fastapi import Depends
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
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow.model.workflow import (
    WorkflowDefinitionCreateRequest,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdateRequest,
)
from app.modules.workflow.model.workflow_version import (
    WorkflowDefinitionVersionRead,
    WorkflowSaveDraftRequest,
)
from app.modules.workflow.service.workflow_service import WorkflowService
from app.modules.workflow.service.workflow_version_service import WorkflowVersionService


@CoolController(
    CoolControllerMeta(
        module="workflow",
        resource="definition",
        scope="admin",
        service=WorkflowService,
        tags=("workflow", "definition"),
        code_prefix="workflow_definition",
        list_response_model=WorkflowDefinitionRead,
        page_item_model=WorkflowDefinitionRead,
        info_response_model=WorkflowDefinitionRead,
        add_request_model=WorkflowDefinitionCreateRequest,
        add_response_model=WorkflowDefinitionRead,
        update_request_model=WorkflowDefinitionUpdateRequest,
        update_response_model=WorkflowDefinitionRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("code", "name", "description"),
            field_eq=(QueryFieldConfig(column="is_active", request_param="status"),),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowDefinitionController(BaseController):
    @Post("/saveDraft", summary="保存草稿", permission="workflow:definition:update")
    def save_draft(
        self,
        payload: WorkflowSaveDraftRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """保存草稿（editor 保存入口）。无草稿建 draft 版本，有则覆盖；同步 code/name/description。"""
        version = WorkflowVersionService(session).save_draft(
            payload.definition_id,
            payload.graph_json,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            current_user=current_user,
        )
        return WorkflowDefinitionVersionRead.model_validate(version).model_dump(by_alias=True)


router = WorkflowDefinitionController.router
