"""工作流产物 API：按实例/定义分页查询与删除（产物由系统在成功终态落地，无 add/update）。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.workflow.model.workflow_artifact import WorkflowArtifactRead
from app.modules.workflow.service.artifact_crud_service import WorkflowArtifactService


@CoolController(
    CoolControllerMeta(
        module="workflow",
        resource="artifact",
        scope="admin",
        service=WorkflowArtifactService,
        tags=("workflow",),
        code_prefix="workflow_artifact",
        list_response_model=WorkflowArtifactRead,
        page_item_model=WorkflowArtifactRead,
        info_response_model=WorkflowArtifactRead,
        actions=("page", "info", "delete"),
        page_query=QueryConfig(
            field_eq=(
                QueryFieldConfig(column="instance_id", request_param="instanceId"),
                QueryFieldConfig(column="definition_id", request_param="definitionId"),
                QueryFieldConfig(column="asset_type", request_param="assetType"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "asc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowArtifactController(BaseController):
    pass


router = WorkflowArtifactController.router
