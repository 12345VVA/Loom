"""
统一 AI API 调用入口。
"""

import logging
from functools import partial

from fastapi import Depends, HTTPException, status
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from app.core.database import Session as DbSession
from app.core.database import engine, get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.framework.runtime import FrameworkRuntimeError, registry
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
from app.modules.base.service.authority_service import (
    get_cached_user_permissions,
    is_super_admin,
)
from app.modules.base.service.security_service import get_current_user

logger = logging.getLogger(__name__)

AI_INVOKE_PERMISSION = "ai:model:invoke"

# 媒体资产转存回调的 registry 名（media 模块在 main.py 装配期注册）
MEDIA_INGEST_CALLBACK = "media_ingest_ai_result"


def _ingest_media_result(
    session: Session,
    *,
    result: dict,
    request_payload: dict,
    current_user_id: int | None,
    profile_code: str | None,
) -> None:
    """同步生图结果的媒体资产写入（registry 回调解耦，ai 不 import media）。

    回调由 media 模块在应用装配期注册；未注册（未装配）或执行失败均仅记日志，
    不影响生图主流程（与原内联写入的失败容忍口径一致）。归属字段经回调透传，
    ai 侧不感知媒体模型。
    """
    try:
        callback = registry.resolve(MEDIA_INGEST_CALLBACK)
    except FrameworkRuntimeError:
        logger.warning("媒体资产回调未注册（%s），跳过同步生图资产写入", MEDIA_INGEST_CALLBACK)
        return
    try:
        asset_count = callback(
            session,
            task_type="image",
            result=result,
            request_payload=request_payload,
            source_type="ai_sync",
            created_by=current_user_id,
            profile_code=profile_code,
        )
        logger.info(
            "同步生图媒体资产写入完成",
            extra={
                "execution_mode": "sync_threadpool",
                "request_path": "/aiapi/ai/model/image",
                "profile_code": profile_code,
                "asset_count": asset_count,
            },
        )
    except Exception:
        logger.error(
            "同步生图媒体资产写入失败",
            extra={
                "execution_mode": "sync_threadpool",
                "request_path": "/aiapi/ai/model/image",
                "profile_code": profile_code,
            },
            exc_info=True,
        )


def require_ai_call_permission(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    """校验当前用户是否拥有 AI 调用权限，未授权返回 403。"""
    if is_super_admin(session, current_user):
        return current_user
    permissions = get_cached_user_permissions(session, current_user)
    if AI_INVOKE_PERMISSION not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无 AI 调用权限")
    return current_user


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
    def chat(
        self,
        payload: AiChatRequest,
        current_user: User = Depends(require_ai_call_permission),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).chat(payload, current_user=current_user)

    @Post("/streamChat", summary="统一文本模型流式调用")
    async def stream_chat(
        self,
        payload: AiChatRequest,
        current_user: User = Depends(require_ai_call_permission),
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
    def embedding(
        self,
        payload: AiEmbeddingRequest,
        current_user: User = Depends(require_ai_call_permission),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).embedding(payload, current_user=current_user)

    @Post("/image", summary="统一图像模型调用")
    async def image(
        self,
        payload: AiImageRequest,
        current_user: User = Depends(require_ai_call_permission),
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
    def rerank(
        self,
        payload: AiRerankRequest,
        current_user: User = Depends(require_ai_call_permission),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).rerank(payload, current_user=current_user)

    @Post("/audio", summary="统一音频模型调用")
    def audio(
        self,
        payload: AiAudioRequest,
        current_user: User = Depends(require_ai_call_permission),
        session: Session = Depends(get_session),
    ):
        return AiModelRuntimeService(session).audio(payload, current_user=current_user)

    @Post("/video", summary="统一视频模型调用")
    def video(
        self,
        payload: AiVideoRequest,
        current_user: User = Depends(require_ai_call_permission),
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
        _ingest_media_result(
            thread_session,
            result=result,
            request_payload=payload.model_dump(),
            current_user_id=current_user_id,
            profile_code=payload.profile_code,
        )
        return result
