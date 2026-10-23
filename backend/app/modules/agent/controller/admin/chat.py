"""智能体对话 API：chatStream（published SSE）/ stopStream（取消三层语义之一）。

SSE 端点不声明 response_model（StreamingResponse；响应包装中间件按 media_type 自动跳过）。
"""

from typing import Any

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user

_PERM = "agent:chat"


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_id: int
    session_id: int | None = None
    question: str


class ChatStopRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trace_token: str


class StopResponse(BaseModel):
    stopped: bool
    message: str


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@CoolController(
    CoolControllerMeta(
        module="agent",
        resource="chat",
        scope="admin",
        service=AgentRunService,  # 占位（chat 无标准 CRUD 面；真实编排见下方自定义端点）
        tags=("agent", "chat"),
        code_prefix="agent_chat",
        actions=(),
    )
)
class AgentChatController(BaseController):
    @Post("/chatStream", summary="正式对话流式运行（published 快照；受控事件队列）", permission=f"{_PERM}:stream")
    def chat_stream(
        self,
        payload: ChatStreamRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> Any:
        return AgentRunService(session).stream_run(
            profile_id=payload.profile_id,
            session_id=payload.session_id,
            question=payload.question,
            run_mode="published",
            current_user=current_user,
        )

    @Post("/stopStream", summary="停止运行（取消令牌置位；仅本人）", permission=f"{_PERM}:stop")
    def stop_stream(
        self,
        payload: ChatStopRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> StopResponse:
        result = AgentRunService(session).stop_run(payload.trace_token, current_user)
        return StopResponse(**result)


router = AgentChatController.router
