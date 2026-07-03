"""
媒体资源管理接口。
"""

from fastapi import Depends, File, UploadFile
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import create_download_token, get_current_user
from app.modules.media.model.media import MediaAssetCreateRequest, MediaAssetRead, MediaAssetUpdateRequest
from app.modules.media.service.media_service import MediaAssetService


@CoolController(
    CoolControllerMeta(
        module="media",
        resource="asset",
        scope="admin",
        service=MediaAssetService,
        tags=("media", "asset"),
        code_prefix="media_asset",
        list_response_model=MediaAssetRead,
        page_item_model=MediaAssetRead,
        info_response_model=MediaAssetRead,
        add_request_model=MediaAssetCreateRequest,
        add_response_model=MediaAssetRead,
        update_request_model=MediaAssetUpdateRequest,
        update_response_model=MediaAssetRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("file_name", "prompt", "original_url", "storage_url", "error_message"),
            field_eq=("asset_type", "source_type", "status", "source_task_id", "created_by"),
            field_like=("file_name", "prompt", "original_url"),
            order_fields=("created_at", "updated_at", "size_bytes"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        list_query=QueryConfig(
            keyword_like_fields=("file_name", "prompt", "original_url", "storage_url", "error_message"),
            field_eq=("asset_type", "source_type", "status", "source_task_id", "created_by"),
            field_like=("file_name", "prompt", "original_url"),
            order_fields=("created_at", "updated_at", "size_bytes"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class MediaAssetController(BaseController):
    @Post("/upload", summary="上传媒体资源", permission="media:asset:upload")
    def upload(
        self,
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return MediaAssetService(session).upload(file, current_user)

    @Get("/stats", summary="媒体资源统计", permission="media:asset:stats")
    def stats(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        return MediaAssetService(session).stats(current_user)

    @Get("/downloadToken", summary="签发短期下载令牌", permission="media:asset:downloadToken")
    def download_token(
        self,
        current_user: User = Depends(get_current_user),
    ):
        """签发专用下载令牌（type=download，短 TTL），供 /uploads 资源鉴权使用。

        与 access token 隔离：下载令牌权限受限（只能下载）、短时失效，
        避免长期 access token 通过 ?token= 泄露到反代日志/Referer/分享串。
        """
        return {
            "token": create_download_token(current_user),
            "expire": settings.DOWNLOAD_TOKEN_EXPIRE_SECONDS,
        }


router = MediaAssetController.router
