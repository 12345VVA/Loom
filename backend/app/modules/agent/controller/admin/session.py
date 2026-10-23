"""智能体会话管理 API（messages 端点 P5 收口）。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.agent.model.agent import AgentSessionRead
from app.modules.agent.service.runtime.session_service import AgentSessionService


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="session",
        scope="admin",
        service=AgentSessionService,
        tags=("agent", "session"),
        code_prefix="agent_session",
        list_response_model=AgentSessionRead,
        page_item_model=AgentSessionRead,
        info_response_model=AgentSessionRead,
        actions=("page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("title", "session_code"),
            field_eq=(
                QueryFieldConfig("profile_id", "profileId"),
                QueryFieldConfig("run_mode", "runMode"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
    )
)
class AgentSessionController(BaseController):
    pass


router = AgentSessionController.router
