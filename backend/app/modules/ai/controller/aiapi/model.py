"""
统一 AI API 调用入口。
"""

import logging
from functools import partial

from fastapi import Depends
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from app.core.database import Session as DbSession
from app.core.database import engine, get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiImageRequest,
    AiRerankRequest,
    AiVideoRequest,
)
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.security_service import get_current_user
from app.modules.media.service.media_service import MediaAssetService

logger = logging.getLogger(__name__)


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
        logger.info(
            "同步生图接口请求进入",
            extra={
                "scenario": payload.scenario,
                "profile_code": payload.profile_code,
                "options_keys": sorted((payload.options or {}).keys()),
            },
        )
        result = await run_in_threadpool(
            partial(
                _run_sync_image_pipeline,
                payload=payload,
                current_user_id=current_user.id if current_user else None,
            )
        )
        logger.info(
            "同步生图接口调用完成",
            extra={
                "provider": result.get("provider"),
                "model": result.get("model"),
                "profile": result.get("profile"),
                "upstream_request_id": result.get("requestId"),
                "image_count": len(result.get("data") or []),
                "execution_mode": "sync_threadpool",
                "thread_offloaded": True,
                "request_path": "/aiapi/ai/model/image",
                "profile_code": payload.profile_code,
            },
        )
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


def _run_sync_image_pipeline(*, payload: AiImageRequest, current_user_id: int | None) -> dict:
    with DbSession(engine) as thread_session:
        current_user = thread_session.get(User, current_user_id) if current_user_id else None
        logger.info(
            "同步生图线程池任务开始",
            extra={
                "execution_mode": "sync_threadpool",
                "thread_offloaded": True,
                "request_path": "/aiapi/ai/model/image",
                "profile_code": payload.profile_code,
            },
        )
        result = AiModelRuntimeService(thread_session).image(payload, current_user=current_user)
        try:
            logger.info(
                "同步生图开始写入媒体资产",
                extra={
                    "execution_mode": "sync_threadpool",
                    "thread_offloaded": True,
                    "request_path": "/aiapi/ai/model/image",
                    "profile_code": payload.profile_code,
                },
            )
            MediaAssetService(thread_session).create_from_ai_result(
                task_type="image",
                result=result,
                request_payload=payload.model_dump(),
                source_type="ai_sync",
                created_by=current_user_id,
                profile_code=payload.profile_code,
            )
            logger.info(
                "同步生图媒体资产写入完成",
                extra={
                    "execution_mode": "sync_threadpool",
                    "thread_offloaded": True,
                    "request_path": "/aiapi/ai/model/image",
                    "profile_code": payload.profile_code,
                },
            )
        except Exception as exc:
            logger.error(
                "同步生图媒体资产写入失败",
                extra={
                    "execution_mode": "sync_threadpool",
                    "thread_offloaded": True,
                    "request_path": "/aiapi/ai/model/image",
                    "profile_code": payload.profile_code,
                },
                exc_info=exc,
            )
        return result
