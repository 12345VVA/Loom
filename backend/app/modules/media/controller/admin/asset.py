"""
媒体资源管理接口。
"""

import logging
import os
import re

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.framework.router.route_meta import Get, Post, TagTypes
from app.framework.storage import DEFAULT_UPLOAD_DIR
from app.modules.base.model.auth import User
from app.modules.base.service.authority_service import is_super_admin
from app.modules.base.service.security_service import create_download_token, get_current_user
from app.modules.media.model.media import (
    MediaAsset,
    MediaAssetCreateRequest,
    MediaAssetRead,
    MediaAssetUpdateRequest,
)
from app.modules.media.service.media_service import (
    MediaAssetService,
    _download_remote_file,
    _filename_from_url,
    _validate_remote_url,
)

logger = logging.getLogger(__name__)


class RetryAssetRequest(BaseModel):
    id: int


class RetryFailedAssetsRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    window_hours: int = Field(default=24, ge=1, le=168)


def _inline_image_response(declared_mime: str | None, safe_name: str) -> tuple[str, dict[str, str]]:
    """按 MIME 白名单构造响应：仅图片（不含可内嵌脚本的 SVG）允许 inline。

    远程服务器/资产行声明的 Content-Type 不可信：text/html 或 SVG 在应用同源
    inline 渲染可执行脚本（窃取本地存储的令牌），一律降级为附件下载。
    """
    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime.startswith("image/") and mime != "image/svg+xml":
        return mime, {
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        }
    return "application/octet-stream", {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }


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

    @Get(
        "/proxyImage",
        summary="远程媒体安全代理下载",
        permission="media:asset:downloadToken",
        tags=(TagTypes.IGNORE_PERMISSION,),
    )
    def proxy_image(
        self,
        url: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        """代理拉取第三方远程图片二进制，解决前端打包下载时的第三方存储桶跨域 (CORS) 限制。
        若该图片已转存至本地存储，直接返回本地文件，无需重复消耗远程网络请求。
        """
        if not url:
            raise HTTPException(status_code=400, detail="缺少 url 参数")

        # 1. 优先检查本地转存资产：若已成功转存且本地文件存在，直接从本地返回
        if isinstance(session, Session):
            asset = session.exec(
                select(MediaAsset)
                .where(
                    (MediaAsset.original_url == url) | (MediaAsset.storage_url == url),
                    MediaAsset.status == "success",
                    MediaAsset.delete_time == None,  # noqa: E711
                )
                .order_by(MediaAsset.created_at.desc())
            ).first()
            if asset and asset.storage_url:
                uploads_root = str(DEFAULT_UPLOAD_DIR)
                rel_path = asset.storage_url.removeprefix("/uploads/").lstrip("/")
                local_full_path = os.path.abspath(os.path.join(uploads_root, rel_path))
                # 路径包含检查：storage_url 均由服务端生成，仍防御性拦截逃逸（对齐 /uploads 路由）
                try:
                    inside_uploads = os.path.commonpath([uploads_root, local_full_path]) == uploads_root
                except ValueError:
                    # Windows 跨盘符等无法比较的路径一律视为逃逸
                    inside_uploads = False
                # 归属检查与 /uploads 路由一致：按文件级归属（storage_url+created_by）放行。
                # 不能只看匹配行的 created_by——自造资产行可伪造归属（add/update 已收窄受控字段）。
                owned = is_super_admin(session, current_user) or session.exec(
                    select(MediaAsset).where(
                        MediaAsset.storage_url == asset.storage_url,
                        MediaAsset.created_by == current_user.id,
                        MediaAsset.delete_time == None,  # noqa: E711
                    )
                ).first() is not None
                if inside_uploads and owned and os.path.isfile(local_full_path):
                    safe_name = asset.file_name or _filename_from_url(url, asset.mime_type, "image")
                    safe_name = re.sub(r'["\r\n\\]', "_", safe_name)
                    media_type, headers = _inline_image_response(asset.mime_type, safe_name)
                    return FileResponse(local_full_path, media_type=media_type, headers=headers)

        try:
            safe_url, hostname = _validate_remote_url(url)
            content, mime_type = _download_remote_file(safe_url, host_header=hostname)
        except Exception as exc:
            logger.warning("代理拉取远程媒体失败: %s, url: %s", exc, url)
            raise HTTPException(status_code=400, detail=f"无法获取远程媒体内容: {exc}")

        safe_name = _filename_from_url(url, mime_type, "image")
        safe_name = re.sub(r'["\r\n\\]', "_", safe_name)
        media_type, headers = _inline_image_response(mime_type, safe_name)
        return Response(content=content, media_type=media_type, headers=headers)

    @Post("/retry", summary="重试单个转存失败的媒体资产", permission="media:asset:update")
    def retry(
        self,
        payload: RetryAssetRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return MediaAssetService(session).retry_single(payload.id, current_user)

    @Post("/retryFailed", summary="批量重试失败的媒体资产", permission="media:asset:update")
    def retry_failed(
        self,
        payload: RetryFailedAssetsRequest | None = None,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        limit = payload.limit if payload else 100
        window_hours = payload.window_hours if payload else 24
        return MediaAssetService(session).retry_failed(limit=limit, window_hours=window_hours, current_user=current_user)


router = MediaAssetController.router
