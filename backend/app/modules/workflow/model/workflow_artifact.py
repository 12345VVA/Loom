"""工作流产物模型：实例成功终态时由 workflow_output 落地的可管理产物实体。

产物与执行快照（state_data/执行日志）解耦：监控看过程，产物看结果。
图片产物冗余存 storage_url（media 资产被删后仍可溯源展示），media_asset_id
仅作溯源引用；文本/JSON 产物内容超阈值时 offload 到对象存储（content_ref）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column
from sqlmodel import Field
from sqlmodel.sql.sqltypes import AutoString

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity

WORKFLOW_ARTIFACT_TYPES = {"image", "text", "json"}


class WorkflowArtifact(BaseEntity, table=True):
    """工作流实例产物（由 end 节点 workflow_output 自适应分类落地）。"""

    __tablename__ = "workflow_artifact"

    instance_id: int = Field(index=True)
    definition_id: int = Field(index=True)
    version_id: int | None = Field(default=None)
    # 冗余实例的 run_type（production | trial | eval）：测试产物打标可区分/可清理，免 join 实例表
    run_type: str = Field(default="production", index=True, max_length=20)
    node_id: str | None = Field(default=None, max_length=100)  # 产出节点（end）
    user_id: int | None = Field(default=None, index=True)  # 归属用户（列名触发自动数据权限）
    field_key: str = Field(max_length=150)  # workflow_output 顶层字段名
    field_path: str | None = Field(default=None, max_length=200)  # 嵌套路径（如 inner_images.0）
    asset_type: str = Field(default="text", index=True, max_length=20)  # image | text | json
    media_asset_id: int | None = Field(default=None, index=True)  # 图片产物溯源
    storage_url: str | None = Field(default=None, max_length=1000)
    original_url: str | None = Field(default=None, max_length=1000)
    content: str | None = Field(default=None, sa_column=Column("content", AutoString, nullable=True))
    content_ref: str | None = Field(default=None, max_length=500)


class WorkflowArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    instance_id: int
    definition_id: int
    version_id: int | None = None
    run_type: str = "production"
    node_id: str | None = None
    user_id: int | None = None
    field_key: str
    field_path: str | None = None
    asset_type: str
    media_asset_id: int | None = None
    storage_url: str | None = None
    original_url: str | None = None
    content: str | None = None
    content_ref: str | None = None
    created_at: datetime
    updated_at: datetime
