"""run 轨迹（观测）API：page/info 仅本人（验收 21）+ toolLogs 工具明细（3.6 info 内含语义）。"""

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.framework.router.route_meta import Get
from app.modules.agent.model.agent import (
    AgentRunTraceRead,
    AgentToolCallLog,
    AgentToolCallLogRead,
)
from app.modules.agent.service.trace_service import AgentRunTraceService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user


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
    @Get("/toolLogs", summary="run 的工具调用明细（仅本人 trace；观测二级）")
    def tool_logs(
        self,
        trace_id: int,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[AgentToolCallLogRead]:
        from app.modules.agent.model.agent import AgentRunTrace

        trace = session.get(AgentRunTrace, trace_id)
        if trace is None or trace.delete_time is not None:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        if trace.user_id != current_user.id:  # 验收 21：仅本人
            raise HTTPException(status_code=403, detail="仅可查看本人的运行明细")
        rows = session.exec(
            select(AgentToolCallLog).where(AgentToolCallLog.trace_id == trace_id).order_by(AgentToolCallLog.id.asc())  # type: ignore[attr-defined]
        ).all()
        return [AgentToolCallLogRead.model_validate(r) for r in rows]


router = AgentTraceController.router
