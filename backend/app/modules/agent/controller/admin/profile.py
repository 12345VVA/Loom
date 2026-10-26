"""智能体定义管理 API：CRUD + 发布/回滚/启停 + 版本列表 + 调试台（draft SSE）。"""

from typing import Any

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.database import get_session
from app.framework.api.naming import resolve_alias
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
    AgentProfileCreateRequest,
    AgentProfileRead,
    AgentProfileUpdateRequest,
    ProfilePublishRequest,
    ProfileRollbackRequest,
    ProfileToggleEnabledRequest,
)
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user

_PERM = "agent:profile"

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class DebugChatRequest(BaseModel):
    # alias_generator 对齐项目 DTO 惯例（EPS camelCase 入参，走查实测缺它 422）
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    profile_id: int
    session_id: int | None = None
    question: str
    # 附件 media id 列表（与 chatStream 同构；≤4 个，后端逐条校验）
    attachments: list[int] = Field(default=[], max_length=4)


class ProfilePublishResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    snapshot_id: int
    version: int
    snapshot_hash: str


class ProfileToggleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    enabled: bool


class SnapshotVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    version: int
    snapshot_hash: str
    created_at: Any = None


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
    @Post("/publish", summary="发布（锁前移四步：读草稿/组装/校验/切换 isCurrent）", permission=f"{_PERM}:publish")
    def publish(
        self,
        payload: ProfilePublishRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ProfilePublishResponse:
        snapshot = AgentProfileService(session).publish(payload.id, current_user=current_user)
        return ProfilePublishResponse(
            snapshot_id=snapshot.id, version=snapshot.version, snapshot_hash=snapshot.snapshot_hash
        )

    @Post("/rollback", summary="回滚到指定快照（不新建快照，切换 isCurrent 指针）", permission=f"{_PERM}:rollback")
    def rollback(
        self,
        payload: ProfileRollbackRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ProfilePublishResponse:
        target = AgentProfileService(session).rollback(payload.id, payload.snapshot_id, current_user=current_user)
        return ProfilePublishResponse(snapshot_id=target.id, version=target.version, snapshot_hash=target.snapshot_hash)

    @Post("/toggleEnabled", summary="启停（实时运行控制，不被发布快照冻结）", permission=f"{_PERM}:publish")
    def toggle_enabled(
        self,
        payload: ProfileToggleEnabledRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ProfileToggleResponse:
        entity = AgentProfileService(session).toggle_enabled(payload.id, payload.enabled, current_user=current_user)
        return ProfileToggleResponse(id=entity.id, enabled=bool(entity.enabled))

    @Get("/versions", summary="快照版本列表（新→旧；前端回滚选择器数据源）", permission=f"{_PERM}:info")
    def versions(
        self,
        id: int,
        _current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[SnapshotVersionResponse]:
        rows = AgentProfileService(session).list_snapshots(id)
        return [
            SnapshotVersionResponse(id=s.id, version=s.version, snapshot_hash=s.snapshot_hash, created_at=s.created_at)
            for s in rows
        ]

    @Post("/debugChat", summary="调试台（draft 草稿试聊，SSE 受控事件流）", permission=f"{_PERM}:debugChat")
    def debug_chat(
        self,
        payload: DebugChatRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> Any:
        return AgentRunService(session).stream_run(
            profile_id=payload.profile_id,
            session_id=payload.session_id,
            question=payload.question,
            attachments=payload.attachments,
            run_mode="draft",
            current_user=current_user,
        )


router = AgentProfileController.router
