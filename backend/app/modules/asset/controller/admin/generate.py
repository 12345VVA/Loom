"""IP 资产库测试页生成入口（方案 B：后端统一经 Composer，评审拍板 P0-2）。

sync 分支照抄 aiapi 控制器 `_run_sync_image_pipeline` 的媒体转存步骤（registry 回调
`media_ingest_ai_result`），不重写转存逻辑；task 分支组装时机=请求时，任务体携带
组装产物与指纹，执行期不再二次组装（与预览所见一致）。ai 后端零改动（仅服务层调用）。
"""

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.core.database import Session as DbSession
from app.core.database import engine, get_session
from app.framework.api.naming import resolve_alias
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta
from app.framework.router.route_meta import Post
from app.framework.runtime import FrameworkRuntimeError, registry
from app.modules.asset.controller.admin.composer import _NoopService, asset_error_to_http
from app.modules.asset.model.asset import AssetCharacter, AssetScene, AssetStyle
from app.modules.asset.service import composer
from app.modules.asset.service.composer import AssetError
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user

MEDIA_INGEST_CALLBACK = "media_ingest_ai_result"


class AssetImageGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    character_id: int | None = None
    scene_id: int | None = None
    style_id: int | None = None
    prompt: str = ""
    variables: dict[str, str] | None = None
    profile_code: str | None = None
    size: str | None = None  # 用户显式覆盖（P0-1，映射 user_size）
    scenario: str = "default"
    mode: str = "sync"  # sync | task


class AssetGenerateImageResponse(BaseModel):
    """透传厂商结果形态（extra=allow 保留上游全部键）+ 资产回链三键。"""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    asset_refs: dict[str, int] = {}
    composed_prompt_hash: str | None = None
    composer_version: str | None = None


def _compose_request(session: Session, payload: AssetImageGenerateRequest, current_user: User):
    """公共组装：加载资产 → ComposeInput → compose()。"""
    input_ = composer.ComposeInput(
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
    return composer.compose(session, input_)


def _call_options(composed: composer.ComposeResult, size: str | None, scenario: str) -> dict:
    """回链三键 + 生效 size + 负面词并入调用 options（经 request_payload 落回链与日志）。"""
    options: dict = {"scenario": scenario}
    effective_size = composed.effective_size or size
    if effective_size:
        options["size"] = effective_size
    if composed.negative_prompt:
        options["negative_prompt"] = composed.negative_prompt
    options.update(
        {
            "asset_refs": composed.asset_refs,
            "composed_prompt_hash": composed.composed_prompt_hash,
            "composer_version": composed.composer_version,
        }
    )
    return options


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="generate",
        scope="admin",
        service=_NoopService,
        tags=("asset", "generate"),
        code_prefix="asset_generate",
        actions=(),
    )
)
class AssetGenerateController(BaseController):
    @Post(
        "/image",
        summary="资产引用生图（组装→同步调用或异步任务，回链指纹统一落库）",
        permission="asset:generate:image",
    )
    def image(
        self,
        payload: AssetImageGenerateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AssetGenerateImageResponse:
        try:
            composed = _compose_request(session, payload, current_user)
        except AssetError as exc:
            raise asset_error_to_http(exc) from exc

        options = _call_options(composed, payload.size, payload.scenario)
        if payload.mode == "task":
            return self._submit_task(session, payload, current_user, composed, options)
        return self._run_sync(payload, current_user, composed, options)

    def _run_sync(
        self, payload: AssetImageGenerateRequest, current_user: User, composed, options: dict
    ) -> AssetGenerateImageResponse:
        """sync 分支：runtime.image → registry 媒体回调（照抄 aiapi `_run_sync_image_pipeline`）。"""
        from app.modules.ai.model.ai import AiImageRequest
        from app.modules.ai.service.runtime_service import AiModelRuntimeService

        image_request = AiImageRequest(
            scenario=payload.scenario,
            profile_code=payload.profile_code,
            prompt=composed.prompt,
            image=composed.reference_images or None,
            options=options,
        )
        with DbSession(engine) as thread_session:
            user = thread_session.get(User, current_user.id) if current_user else None
            result = AiModelRuntimeService(thread_session).image(image_request, current_user=user)
            try:
                callback = registry.resolve(MEDIA_INGEST_CALLBACK)
            except FrameworkRuntimeError:
                callback = None
            if callback is not None:
                try:
                    callback(
                        thread_session,
                        task_type="image",
                        result=result,
                        request_payload=image_request.model_dump(),
                        source_type="ai_sync",
                        created_by=current_user.id if current_user else None,
                        profile_code=payload.profile_code,
                    )
                except Exception:  # noqa: BLE001——转存失败不阻断生图主流程（与 aiapi 同口径）
                    pass
        return AssetGenerateImageResponse(
            **{
                **result,
                "asset_refs": composed.asset_refs,
                "composed_prompt_hash": composed.composed_prompt_hash,
                "composer_version": composed.composer_version,
            }
        )

    def _submit_task(
        self, session: Session, payload: AssetImageGenerateRequest, current_user: User, composed, options: dict
    ) -> AssetGenerateImageResponse:
        """task 分支：组装产物入任务体，执行期不再二次组装（与预览所见一致）。"""
        from app.modules.ai.model.ai import AiTaskSubmitRequest
        from app.modules.ai.service.task_service import AiTaskService

        submit_payload = {
            "prompt": composed.prompt,
            "image": composed.reference_images or None,
            "options": options,
        }
        result = AiTaskService(session).submit(
            AiTaskSubmitRequest(
                task_type="image",
                scenario=payload.scenario,
                profile_code=payload.profile_code,
                payload=submit_payload,
            ),
            current_user=current_user,
        )
        return AssetGenerateImageResponse(
            **{
                **result,
                "asset_refs": composed.asset_refs,
                "composed_prompt_hash": composed.composed_prompt_hash,
                "composer_version": composed.composer_version,
            }
        )


router = AssetGenerateController.router
