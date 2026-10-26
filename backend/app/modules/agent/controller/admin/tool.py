"""工具资源层 API：清单/启停/刷新/注册表状态。

- refresh 仅做资源层 DB sync（不重建执行注册表，评审 v1.4 语义消歧）；
- registryStatus 暴露 degraded 状态（启动收集失败时管理面可见）。
"""

from fastapi import Depends
from pydantic import BaseModel
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
from app.modules.agent.model.agent import (
    AgentToolResourceRead,
    AgentToolResourceVersionRead,
    ToolToggleRequest,
)
from app.modules.agent.service.tool_registry import registry_status, sync_resources
from app.modules.agent.service.tool_service import AgentToolResourceService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


class RegistryStatusResponse(BaseModel):
    degraded: bool
    error: str | None = None
    toolCount: int
    tools: list[str]


class ToolSyncResponse(BaseModel):
    ok: bool
    count: int = 0
    message: str = "ok"


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
    @Post("/toggleEnabled", summary="工具启停（实时运行控制，D14 紧急禁用立即生效）", permission="agent:tool:toggle")
    def toggle_enabled(
        self,
        payload: ToolToggleRequest,
        _current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AgentToolResourceRead:
        service = AgentToolResourceService(session)
        entity = session.get(service.model, payload.id)
        if entity is None or entity.delete_time is not None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="工具不存在")
        entity.status = payload.status
        session.add(entity)
        session.commit()
        session.refresh(entity)
        return AgentToolResourceRead.model_validate(entity)

    @Post("/refresh", summary="资源层同步（仅 DB sync，不重建执行注册表）", permission="agent:tool:refresh")
    def refresh(
        self,
        _current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ToolSyncResponse:
        result = sync_resources(session, operator_id=_current_user.id)
        return ToolSyncResponse(ok=True, count=result["count"], message="资源层同步完成")

    @Get("/registryStatus", summary="执行注册表状态（degraded 可见性）", permission="agent:tool:list")
    def registry_status(
        self,
        _current_user: User = Depends(get_current_user),
    ) -> RegistryStatusResponse:
        return RegistryStatusResponse(**registry_status())

    @Get("/versions", summary="工具资源版本历史（E12：双哈希分类变更线，倒序）", permission="agent:tool:list")
    def versions(
        self,
        toolName: str,
        _current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[AgentToolResourceVersionRead]:
        from sqlmodel import select

        from app.modules.agent.model.agent import AgentToolResourceVersion

        rows = session.exec(
            select(AgentToolResourceVersion)
            .where(AgentToolResourceVersion.tool_name == toolName)
            .order_by(AgentToolResourceVersion.version.desc())  # type: ignore[attr-defined]
        ).all()
        return [AgentToolResourceVersionRead.model_validate(r) for r in rows]


router = AgentToolController.router
