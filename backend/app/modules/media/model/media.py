"""
媒体资源模型。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity

MEDIA_ASSET_TYPES = {"image", "video", "audio", "file"}
MEDIA_SOURCE_TYPES = {"ai_task", "ai_sync", "upload"}
MEDIA_ASSET_STATUSES = {"pending", "transferring", "success", "failed", "deleted"}


class MediaAsset(BaseEntity, table=True):
    __tablename__ = "media_asset"

    asset_type: str = Field(default="file", index=True, max_length=50)
    source_type: str = Field(default="upload", index=True, max_length=50)
    source_task_id: int | None = Field(default=None, index=True)
    provider_code: str | None = Field(default=None, index=True, max_length=100)
    model_code: str | None = Field(default=None, index=True, max_length=150)
    profile_code: str | None = Field(default=None, index=True, max_length=100)
    original_url: str | None = Field(default=None, max_length=1000)
    storage_url: str | None = Field(default=None, index=True, max_length=1000)
    file_name: str | None = Field(default=None, index=True, max_length=255)
    mime_type: str | None = Field(default=None, index=True, max_length=100)
    md5: str | None = Field(default=None, index=True, max_length=32)
    size_bytes: int = Field(default=0)
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    prompt: str | None = None
    params_payload: str | None = None
    status: str = Field(default="pending", index=True, max_length=50)
    error_message: str | None = Field(default=None, max_length=1000)
    created_by: int | None = Field(default=None, index=True)


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    asset_type: str
    source_type: str
    source_task_id: int | None = None
    provider_code: str | None = None
    model_code: str | None = None
    profile_code: str | None = None
    original_url: str | None = None
    storage_url: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    md5: str | None = None
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    prompt: str | None = None
    params_payload: str | None = None
    status: str
    error_message: str | None = None
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class MediaAssetCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    asset_type: str = "file"
    source_type: str = "upload"
    source_task_id: int | None = None
    provider_code: str | None = None
    model_code: str | None = None
    profile_code: str | None = None
    original_url: str | None = None
    storage_url: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    md5: str | None = None
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    prompt: str | None = None
    params_payload: str | None = None
    status: str = "pending"
    error_message: str | None = None
    created_by: int | None = None


class MediaAssetUpdateRequest(MediaAssetCreateRequest):
    id: int


class MediaAssetUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    url: str
    name: str
    asset: MediaAssetRead


class MediaAssetStatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    type_counts: dict[str, int] = PydanticField(default_factory=dict)
    status_counts: dict[str, int] = PydanticField(default_factory=dict)
    source_counts: dict[str, int] = PydanticField(default_factory=dict)
