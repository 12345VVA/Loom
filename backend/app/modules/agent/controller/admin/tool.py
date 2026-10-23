"""工具资源层 API：list 含 degraded 状态（P2 接 tool_registry）；启停/刷新端点 P2 收口。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.agent.model.agent import AgentToolResourceRead
from app.modules.agent.service.tool_service import AgentToolResourceService


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="tool",
        scope="admin",
        service=AgentToolResourceService,
        tags=("agent", "tool"),
        code_prefix="agent_tool",
        list_response_model=AgentToolResourceRead,
        page_item_model=AgentToolResourceRead,
        info_response_model=AgentToolResourceRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("tool_name", "display_name"),
            field_eq=(
                QueryFieldConfig("level", "level"),
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("source_type", "sourceType"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AgentToolController(BaseController):
    pass


router = AgentToolController.router
