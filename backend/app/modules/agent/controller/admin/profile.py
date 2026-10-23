"""智能体定义管理 API（发布/回滚/启停/调试台端点 P5 收口）。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.agent.model.agent import (
    AgentProfileCreateRequest,
    AgentProfileRead,
    AgentProfileUpdateRequest,
)
from app.modules.agent.service.profile_service import AgentProfileService

_PERM = "agent:profile"


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="profile",
        scope="admin",
        service=AgentProfileService,
        tags=("agent", "profile"),
        code_prefix="agent_profile",
        list_response_model=AgentProfileRead,
        page_item_model=AgentProfileRead,
        info_response_model=AgentProfileRead,
        add_request_model=AgentProfileCreateRequest,
        add_response_model=AgentProfileRead,
        update_request_model=AgentProfileUpdateRequest,
        update_response_model=AgentProfileRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("name", "code"),
            field_eq=(
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("enabled", "enabled"),
            ),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class AgentProfileController(BaseController):
    pass


router = AgentProfileController.router
