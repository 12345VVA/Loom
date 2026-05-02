"""
统一 AI API 调用入口。
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import AiAudioRequest, AiChatRequest, AiEmbeddingRequest, AiImageRequest, AiRerankRequest, AiVideoRequest
from app.modules.ai.service.ai_service import AiModelRuntimeService
from app.modules.base.service.admin_service import BaseAdminCrudService


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
    async def chat(self, payload: AiChatRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).chat(payload)

    @Post("/embedding", summary="统一向量模型调用")
    async def embedding(self, payload: AiEmbeddingRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).embedding(payload)

    @Post("/image", summary="统一图像模型调用")
    async def image(self, payload: AiImageRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).image(payload)

    @Post("/rerank", summary="统一重排模型调用")
    async def rerank(self, payload: AiRerankRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).rerank(payload)

    @Post("/audio", summary="统一音频模型调用")
    async def audio(self, payload: AiAudioRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).audio(payload)

    @Post("/video", summary="统一视频模型调用")
    async def video(self, payload: AiVideoRequest, session: Session = Depends(get_session)):
        return AiModelRuntimeService(session).video(payload)


router = AiRuntimeController.router
