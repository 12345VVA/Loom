"""
统一 AI API 调用入口。
"""
from fastapi import Depends
from sqlmodel import Session
from starlette.responses import StreamingResponse

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiAudioRequest, AiChatRequest, AiEmbeddingRequest, AiImageRequest, AiRerankRequest, AiVideoRequest
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.media.service.media_service import MediaAssetService


class _NoopService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, None)


@CoolController(
    CoolControllerMeta(
        module="ai",
        resource="model",
        scope="aiapi",
        service=_NoopService,
        tags=("ai", "runtime"),
        code_prefix="ai_runtime_model",
        actions=(),
    )
)
class AiRuntimeController(BaseController):
    @Post("/chat", summary="统一文本模型调用")
    async def chat(
        self,
        payload: AiChatRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).chat(payload, current_user=current_user)

    @Post("/streamChat", summary="统一文本模型流式调用")
    async def stream_chat(
        self,
        payload: AiChatRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return StreamingResponse(
            AiModelRuntimeService(session).stream_chat(payload, current_user=current_user),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @Post("/embedding", summary="统一向量模型调用")
    async def embedding(
        self,
        payload: AiEmbeddingRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).embedding(payload, current_user=current_user)

    @Post("/image", summary="统一图像模型调用")
    async def image(
        self,
        payload: AiImageRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        result = AiModelRuntimeService(session).image(payload, current_user=current_user)
        try:
            MediaAssetService(session).create_from_ai_result(
                task_type="image",
                result=result,
                request_payload=payload.model_dump(),
                source_type="ai_sync",
                created_by=current_user.id if current_user else None,
                profile_code=payload.profile_code,
            )
        except Exception:
            pass
        return result

    @Post("/rerank", summary="统一重排模型调用")
    async def rerank(
        self,
        payload: AiRerankRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).rerank(payload, current_user=current_user)

    @Post("/audio", summary="统一音频模型调用")
    async def audio(
        self,
        payload: AiAudioRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).audio(payload, current_user=current_user)

    @Post("/video", summary="统一视频模型调用")
    async def video(
        self,
        payload: AiVideoRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).video(payload, current_user=current_user)


router = AiRuntimeController.router
