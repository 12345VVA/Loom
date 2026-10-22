"""资产组装预览 API（透明组装：前端预览必须走本端点，禁复刻拼接逻辑——决策 #26）。"""

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.core.database import get_session
from app.framework.api.naming import resolve_alias
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.modules.asset.model.asset import AssetCharacter, AssetScene, AssetStyle
from app.modules.asset.service import composer
from app.modules.asset.service.composer import (
    AssetError,
    AssetNotFoundError,
    ComposeInput,
)
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.security_service import get_current_user


class _NoopService(BaseAdminCrudService):
    """纯自定义端点资源，无标准 CRUD（照抄 ai dashboard 先例）。"""

    def __init__(self, session: Session):
        super().__init__(session, None)


class ComposerPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    character_id: int | None = None
    scene_id: int | None = None
    style_id: int | None = None
    prompt: str = ""
    variables: dict[str, str] | None = None
    profile_code: str | None = None
    size: str | None = None  # 用户显式覆盖（P0-1）


class ComposerPreviewResponse(BaseModel):
    """组装预览响应（契约 = ComposeResult.to_payload，设计附录 B）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    prompt: str
    negative_prompt: str
    reference_images: list[str] = []
    effective_size: str | None = None
    warnings: list[dict[str, str]] = []
    composed_prompt_hash: str
    composer_version: str
    segments: list[dict] = []
    reference_segments: list[dict] = []
    asset_refs: dict[str, int] = {}


def asset_error_to_http(exc: AssetError) -> HTTPException:
    """AssetError → HTTPException：not-found 404，其余 400；中文 detail 直出不再包装。"""
    status = 404 if isinstance(exc, AssetNotFoundError) else 400
    return HTTPException(status_code=status, detail=str(exc))


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="composer",
        scope="admin",
        service=_NoopService,
        tags=("asset", "composer"),
        code_prefix="asset_composer",
        actions=(),
    )
)
class AssetComposerController(BaseController):
    @Post("/preview", summary="资产组装预览（prompt/负面/参考图/warnings/指纹）", permission="asset:composer:preview")
    def preview(
        self,
        payload: ComposerPreviewRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ComposerPreviewResponse:
        try:
            input_ = ComposeInput(
                character=composer.fetch_validated(session, AssetCharacter, payload.character_id)
                if payload.character_id
                else None,
                scene=composer.fetch_validated(session, AssetScene, payload.scene_id) if payload.scene_id else None,
                style=composer.fetch_validated(session, AssetStyle, payload.style_id) if payload.style_id else None,
                user_prompt=payload.prompt,
                variables=payload.variables or {},
                current_user_id=current_user.id if current_user else 0,
                profile_code=payload.profile_code,
                user_size=payload.size,
            )
            result = composer.compose(session, input_)
        except AssetError as exc:
            raise asset_error_to_http(exc) from exc
        return ComposerPreviewResponse(**result.to_payload())


router = AssetComposerController.router
