"""
媒体资源模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField
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
    source_task_id: Optional[int] = Field(default=None, index=True)
    provider_code: Optional[str] = Field(default=None, index=True, max_length=100)
    model_code: Optional[str] = Field(default=None, index=True, max_length=150)
    profile_code: Optional[str] = Field(default=None, index=True, max_length=100)
    original_url: Optional[str] = Field(default=None, max_length=1000)
    storage_url: Optional[str] = Field(default=None, index=True, max_length=1000)
    file_name: Optional[str] = Field(default=None, index=True, max_length=255)
    mime_type: Optional[str] = Field(default=None, index=True, max_length=100)
    md5: Optional[str] = Field(default=None, index=True, max_length=32)
    size_bytes: int = Field(default=0)
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    prompt: Optional[str] = None
    params_payload: Optional[str] = None
    status: str = Field(default="pending", index=True, max_length=50)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    created_by: Optional[int] = Field(default=None, index=True)


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    asset_type: str
    source_type: str
    source_task_id: Optional[int] = None
    provider_code: Optional[str] = None
    model_code: Optional[str] = None
    profile_code: Optional[str] = None
    original_url: Optional[str] = None
    storage_url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    md5: Optional[str] = None
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    prompt: Optional[str] = None
    params_payload: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class MediaAssetCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    asset_type: str = "file"
    source_type: str = "upload"
    source_task_id: Optional[int] = None
    provider_code: Optional[str] = None
    model_code: Optional[str] = None
    profile_code: Optional[str] = None
    original_url: Optional[str] = None
    storage_url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    md5: Optional[str] = None
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    prompt: Optional[str] = None
    params_payload: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None
    created_by: Optional[int] = None


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
