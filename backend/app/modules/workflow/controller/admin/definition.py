"""
工作流定义管理 API 接口。
"""
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.workflow.model.workflow import (
    WorkflowDefinitionCreateRequest,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdateRequest,
)
from app.modules.workflow.service.workflow_service import WorkflowService


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
            field_eq=(
                QueryFieldConfig(column="is_active", request_param="status"),
            ),
            field_like=("code", "name"),
            order_fields=("created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowDefinitionController(BaseController):
    pass


router = WorkflowDefinitionController.router
