"""run 轨迹（观测）API：page/info 仅本人（验收 21，service 层限定）。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.agent.model.agent import AgentRunTraceRead
from app.modules.agent.service.trace_service import AgentRunTraceService


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="trace",
        scope="admin",
        service=AgentRunTraceService,
        tags=("agent", "trace"),
        code_prefix="agent_trace",
        list_response_model=AgentRunTraceRead,
        page_item_model=AgentRunTraceRead,
        info_response_model=AgentRunTraceRead,
        actions=("page", "info"),
        page_query=QueryConfig(
            field_eq=(
                QueryFieldConfig("profile_id", "profileId"),
                QueryFieldConfig("run_mode", "runMode"),
                QueryFieldConfig("status", "status"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AgentTraceController(BaseController):
    pass


router = AgentTraceController.router
