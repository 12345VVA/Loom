"""
媒体资源服务。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import mimetypes
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.core.config import settings
from app.framework.storage import StorageService, UploadRejectedError
from app.modules.ai.model.ai import AiGenerationTask
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.authority_service import is_super_admin
from app.modules.media.model.media import MEDIA_ASSET_TYPES, MediaAsset


@dataclass
class MediaArtifact:
    asset_type: str
    original_url: str | None = None
    b64_data: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


class MediaAssetService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, MediaAsset)

    def upload(self, file: UploadFile, current_user: User | None = None) -> dict:
        content = _read_upload_file(file)
        try:
            storage_url = StorageService.get_instance().upload(content, file.filename or "upload.bin")
        except UploadRejectedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        asset = MediaAsset(
            asset_type=_asset_type_from_mime_or_name(file.content_type, file.filename),
            source_type="upload",
            storage_url=storage_url,
            file_name=file.filename,
            mime_type=file.content_type or mimetypes.guess_type(file.filename or "")[0],
            md5=_md5(content),
            size_bytes=len(content),
            status="success",
            created_by=current_user.id if current_user else None,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return {"id": asset.id, "url": storage_url, "name": file.filename, "asset": self._finalize_data(asset.model_dump())}

    def delete(self, ids: list[int], payload: Any = None, soft_delete: bool | None = None) -> dict:
        assets = list(self.session.exec(select(MediaAsset).where(MediaAsset.id.in_(ids), MediaAsset.delete_time == None)).all())  # noqa: E711
        delete_results: dict[int, bool] = {}
        failed_ids: list[int] = []
        deletable_ids: list[int] = []
        for asset in assets:
            try:
                storage_deleted = StorageService.get_instance().delete(asset.storage_url) if asset.storage_url else True
            except Exception as exc:
                storage_deleted = False
                asset.error_message = f"存储文件删除失败: {exc}"[:1000]
            if storage_deleted:
                delete_results[asset.id] = True
                asset.status = "deleted"
                asset.error_message = None
                deletable_ids.append(asset.id)
            else:
                delete_results[asset.id] = False
                failed_ids.append(asset.id)
                asset.error_message = asset.error_message or "存储文件删除失败"
            self.session.add(asset)
        self.session.commit()
        result = super().delete(deletable_ids, payload=payload, soft_delete=True) if deletable_ids else {"success": True, "deleted_ids": []}
        result["storageDeleteResults"] = delete_results
        result["failedIds"] = failed_ids
        result["success"] = not failed_ids
        return result

    def stats(self, current_user: User | None = None) -> dict:
        statement = select(MediaAsset).where(MediaAsset.delete_time == None)  # noqa: E711
        if current_user and not is_super_admin(self.session, current_user):
            statement = statement.where(MediaAsset.created_by == current_user.id)
        rows = list(self.session.exec(statement).all())
        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        for item in rows:
            type_counts[item.asset_type] = type_counts.get(item.asset_type, 0) + 1
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
            source_counts[item.source_type] = source_counts.get(item.source_type, 0) + 1
        return {"typeCounts": type_counts, "statusCounts": status_counts, "sourceCounts": source_counts}

    def create_from_ai_task(self, task: AiGenerationTask) -> list[MediaAsset]:
        if task.status != "success" or not task.result_payload:
            return []

        result = _loads_json(task.result_payload)
        request = _loads_json(task.request_payload)
        return self.create_from_ai_result(
            task_type=task.task_type,
            result=result,
            request_payload=request,
            source_type="ai_task",
            created_by=task.created_by,
            source_task_id=task.id,
            profile_code=task.profile_code,
        )

    def create_from_ai_result(
        self,
        *,
        task_type: str,
        result: dict,
        request_payload: dict,
        source_type: str,
        created_by: int | None = None,
        source_task_id: int | None = None,
        profile_code: str | None = None,
    ) -> list[MediaAsset]:
        artifacts = _extract_artifacts(result, task_type)
        assets: list[MediaAsset] = []

        for artifact in artifacts:
            asset = MediaAsset(
                asset_type=artifact.asset_type,
                source_type=source_type,
                source_task_id=source_task_id,
                original_url=artifact.original_url,
                file_name=artifact.file_name,
                mime_type=artifact.mime_type,
                width=artifact.width,
                height=artifact.height,
                duration_seconds=artifact.duration_seconds,
                prompt=request_payload.get("prompt") or request_payload.get("input"),
                params_payload=json.dumps(request_payload.get("options") or {}, ensure_ascii=False),
                provider_code=result.get("provider"),
                model_code=result.get("model"),
                profile_code=result.get("profile") or profile_code,
                status="transferring",
                created_by=created_by,
            )
            self.session.add(asset)
            self.session.commit()
            self.session.refresh(asset)
            try:
                self._transfer_artifact(asset, artifact)
            except Exception as exc:  # 转存失败不能影响 AI 任务状态
                asset.status = "failed"
                asset.error_message = str(exc)[:1000]
                self.session.add(asset)
                self.session.commit()
            assets.append(asset)
        return assets

    def _transfer_artifact(self, asset: MediaAsset, artifact: MediaArtifact) -> None:
        if artifact.original_url:
            _validate_remote_url(artifact.original_url)
            content, mime_type = _download_remote_file(artifact.original_url)
            file_name = artifact.file_name or _filename_from_url(artifact.original_url, mime_type, artifact.asset_type)
            asset.original_url = artifact.original_url
        elif artifact.b64_data:
            content, mime_type = _decode_base64_payload(artifact.b64_data, artifact.mime_type)
            file_name = artifact.file_name or _default_filename(mime_type, artifact.asset_type)
        else:
            raise ValueError("未找到可转存的媒体内容")

        asset.mime_type = asset.mime_type or mime_type
        asset.file_name = file_name
        asset.size_bytes = len(content)
        asset.md5 = _md5(content)
        _ensure_media_size(content)
        existing = self._find_existing_asset(asset)
        if existing:
            self.session.delete(asset)
            self.session.commit()
            return
        asset.storage_url = StorageService.get_instance().save(content, file_name)
        asset.status = "success"
        asset.error_message = None
        self.session.add(asset)
        self.session.commit()

    def _find_existing_asset(self, asset: MediaAsset) -> MediaAsset | None:
        if not asset.md5:
            return None
        statement = (
            select(MediaAsset)
            .where(
                MediaAsset.id != asset.id,
                MediaAsset.delete_time == None,  # noqa: E711
                MediaAsset.status == "success",
                MediaAsset.source_type == asset.source_type,
                MediaAsset.md5 == asset.md5,
            )
            .order_by(MediaAsset.created_at.desc())
        )
        return self.session.exec(statement).first()


def _read_upload_file(file: UploadFile) -> bytes:
    content = file.file.read()
    file.file.seek(0)
    return content


def _md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _loads_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_artifacts(value: Any, task_type: str) -> list[MediaArtifact]:
    result: list[MediaArtifact] = []
    for item in _walk_json(value):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("image_url") or item.get("imageUrl") or item.get("video_url") or item.get("audio_url")
        b64 = item.get("b64_json") or item.get("b64Json") or item.get("base64")
        if not url and not b64:
            continue
        asset_type = _asset_type_from_payload(item, task_type, url)
        result.append(
            MediaArtifact(
                asset_type=asset_type,
                original_url=url,
                b64_data=b64,
                mime_type=item.get("mime_type") or item.get("mimeType"),
                file_name=item.get("file_name") or item.get("fileName"),
                width=_int_or_none(item.get("width")),
                height=_int_or_none(item.get("height")),
                duration_seconds=_float_or_none(item.get("duration") or item.get("duration_seconds") or item.get("durationSeconds")),
            )
        )
    return result


def _walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持 http/https 媒体 URL")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("不允许转存本地地址")

    hostname = parsed.hostname.lower().rstrip(".")
    is_allowed_host = _is_allowed_remote_host(hostname)
    proxy_network = ipaddress.ip_network("198.18.0.0/15")
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("媒体 URL 域名解析失败") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip in proxy_network and is_allowed_host:
            continue
        if not ip.is_global:
            raise ValueError("不允许转存内网地址")


def _is_allowed_remote_host(hostname: str) -> bool:
    for pattern in _remote_allowed_host_patterns():
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if hostname.endswith(suffix) and hostname != suffix.lstrip("."):
                return True
            continue
        if hostname == pattern:
            return True
    return False


def _remote_allowed_host_patterns() -> list[str]:
    return [
        item.strip().lower().rstrip(".")
        for item in (settings.MEDIA_REMOTE_ALLOWED_HOSTS or "").split(",")
        if item.strip()
    ]


def _download_remote_file(url: str) -> tuple[bytes, str | None]:
    max_bytes = settings.MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB * 1024 * 1024
    timeout = settings.MEDIA_REMOTE_DOWNLOAD_TIMEOUT_SECONDS
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
        if response.is_redirect:
            raise ValueError("远程媒体 URL 不允许重定向")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0] or None
        length = response.headers.get("content-length")
        if length and int(length) > max_bytes:
            raise ValueError(f"远程媒体超过 {settings.MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB}MB 限制")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"远程媒体超过 {settings.MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB}MB 限制")
            chunks.append(chunk)
    return b"".join(chunks), content_type


def _decode_base64_payload(payload: str, fallback_mime: str | None = None) -> tuple[bytes, str | None]:
    mime_type = fallback_mime
    data = payload
    if payload.startswith("data:") and "," in payload:
        header, data = payload.split(",", 1)
        mime_type = header.removeprefix("data:").split(";")[0] or fallback_mime
    try:
        return base64.b64decode(data, validate=True), mime_type
    except binascii.Error as exc:
        raise ValueError("base64 媒体内容无法解码") from exc


def _ensure_media_size(content: bytes) -> None:
    max_bytes = settings.MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(f"媒体文件超过 {settings.MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB}MB 限制")


def _asset_type_from_payload(item: dict, task_type: str, url: str | None) -> str:
    declared = item.get("asset_type") or item.get("assetType") or item.get("type")
    if declared in MEDIA_ASSET_TYPES:
        return declared
    if task_type in {"image", "video", "audio"}:
        return task_type
    return _asset_type_from_mime_or_name(item.get("mime_type") or item.get("mimeType"), url)


def _asset_type_from_mime_or_name(mime_type: str | None, name: str | None) -> str:
    mime_type = mime_type or mimetypes.guess_type(name or "")[0] or ""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "file"


def _filename_from_url(url: str, mime_type: str | None, asset_type: str) -> str:
    name = Path(urlparse(url).path).name
    if name and "." in name:
        return name
    return _default_filename(mime_type, asset_type)


def _default_filename(mime_type: str | None, asset_type: str) -> str:
    ext = mimetypes.guess_extension(mime_type or "") or {"image": ".png", "video": ".mp4", "audio": ".mp3"}.get(asset_type, ".bin")
    return f"{asset_type}{ext}"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
