"""IP 资产库风格管理 API。"""

from fastapi import Depends
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
from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_PUBLISHED,
    AssetForkRequest,
    AssetStyleCreateRequest,
    AssetStyleRead,
    AssetStyleUpdateRequest,
    AssetTransitionRequest,
    ReferenceAddRequest,
    ReferenceRemoveRequest,
    ReferenceReorderRequest,
    ReferenceStateResponse,
    ReferenceStatsResponse,
)
from app.modules.asset.service.reference import ReferenceService
from app.modules.asset.service.style_service import AssetStyleService
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user

_SERVICE = AssetStyleService
_PERM = "asset:style"


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="style",
        scope="admin",
        service=_SERVICE,
        tags=("asset", "style"),
        code_prefix="asset_style",
        list_response_model=AssetStyleRead,
        page_item_model=AssetStyleRead,
        info_response_model=AssetStyleRead,
        add_request_model=AssetStyleCreateRequest,
        add_response_model=AssetStyleRead,
        update_request_model=AssetStyleUpdateRequest,
        update_response_model=AssetStyleRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("name", "code"),
            field_like=(QueryFieldConfig("tags", "tags"),),
            field_eq=(
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("category", "category"),
            ),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class AssetStyleController(BaseController):
    @Post("/publish", summary="发布（draft→published）", permission=f"{_PERM}:publish")
    def publish(
        self,
        payload: AssetTransitionRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AssetStyleRead:
        entity = _SERVICE(session).transition_status(payload.id, ASSET_STATUS_PUBLISHED, current_user)
        return AssetStyleRead.model_validate(entity)

    @Post("/archive", summary="归档（published→archived，禁新增引用、存量放行）", permission=f"{_PERM}:archive")
    def archive(
        self,
        payload: AssetTransitionRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AssetStyleRead:
        entity = _SERVICE(session).transition_status(payload.id, ASSET_STATUS_ARCHIVED, current_user)
        return AssetStyleRead.model_validate(entity)

    @Post("/restore", summary="恢复（archived→published）", permission=f"{_PERM}:restore")
    def restore(
        self,
        payload: AssetTransitionRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AssetStyleRead:
        entity = _SERVICE(session).transition_status(payload.id, ASSET_STATUS_PUBLISHED, current_user)
        return AssetStyleRead.model_validate(entity)

    @Post("/fork", summary="复制副本（published→本人 draft，code 随机后缀防冲突）", permission=f"{_PERM}:fork")
    def fork(
        self,
        payload: AssetForkRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> AssetStyleRead:
        entity = _SERVICE(session).fork(payload.id, current_user)
        return AssetStyleRead.model_validate(entity)

    @Post("/addReference", summary="新增参考图（MD5 防重、上限 20）", permission=f"{_PERM}:reference")
    def add_reference(
        self,
        payload: ReferenceAddRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ReferenceStateResponse:
        result = ReferenceService(session, _SERVICE(session)).add_reference(
            payload.id, payload.media_id, payload.role, current_user
        )
        return ReferenceStateResponse(**result)

    @Post("/removeReference", summary="移除参考图", permission=f"{_PERM}:reference")
    def remove_reference(
        self,
        payload: ReferenceRemoveRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ReferenceStateResponse:
        result = ReferenceService(session, _SERVICE(session)).remove_reference(
            payload.id, payload.media_id, current_user
        )
        return ReferenceStateResponse(**result)

    @Post("/reorderReferences", summary="参考图全量重排（拖拽排序提交形态）", permission=f"{_PERM}:reference")
    def reorder_references(
        self,
        payload: ReferenceReorderRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ReferenceStateResponse:
        result = ReferenceService(session, _SERVICE(session)).reorder_references(
            payload.id, payload.media_ids, current_user
        )
        return ReferenceStateResponse(**result)

    @Get("/referenceStats", summary="引用计数（第一阶段：成功产出数，按任务去重）", permission=f"{_PERM}:info")
    def reference_stats(
        self,
        id: int,
        _current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> ReferenceStatsResponse:
        return ReferenceStatsResponse(**_SERVICE(session).reference_stats(id))


router = AssetStyleController.router
