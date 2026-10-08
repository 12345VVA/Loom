"""工作流长期记忆管理 API：四动作 add/delete/page/info（无 update——update 审计断裂
+ 一致性负担，修正走删旧+新增或工作流侧 key upsert，设计 §11/§16 管理面分析）。

管理页是四条防线的处置端：凭据标记 / 共写矛盾软删 / test 残留清理 / injection 排查。
读路径按 definition 归属过滤（DataScope 对无 user_id 列模型不生效，service 层显式过滤）。
"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.workflow.model.workflow_memory import WorkflowMemoryAddRequest, WorkflowMemoryRead
from app.modules.workflow.service.workflow_memory_service import WorkflowMemoryService


@CoolController(
    CoolControllerMeta(
        module="workflow",
        resource="memory",
        scope="admin",
        service=WorkflowMemoryService,
        tags=("workflow", "memory"),
        code_prefix="workflow_memory",
        list_response_model=WorkflowMemoryRead,
        page_item_model=WorkflowMemoryRead,
        info_response_model=WorkflowMemoryRead,
        add_request_model=WorkflowMemoryAddRequest,
        add_response_model=WorkflowMemoryRead,
        actions=("add", "delete", "page", "info"),
        page_query=QueryConfig(
            keyword_like_fields=("content", "memory_key"),
            field_eq=(
                # definitionId：工作流主维度筛选；sourceRunType：trial/admin/test_node/production（§11 一等能力）
                QueryFieldConfig(column="definition_id", request_param="definitionId"),
                QueryFieldConfig(column="memory_env", request_param="memoryEnv"),  # production/test
                QueryFieldConfig(column="memory_type", request_param="memoryType"),
                QueryFieldConfig(column="source_run_type", request_param="sourceRunType"),
            ),
            field_like=("memory_key",),
            order_fields=("created_at", "updated_at", "last_accessed_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowMemoryController(BaseController):
    pass


router = WorkflowMemoryController.router
