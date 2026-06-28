"""
字典模块模型
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class DictType(BaseEntity, table=True):
    """字典类型表"""

    __tablename__ = "dict_type"

    name: str = Field(index=True)  # 名称
    key: str = Field(index=True, unique=True)  # 标识


class DictInfo(BaseEntity, table=True):
    """字典数据表"""

    __tablename__ = "dict_info"

    type_id: int = Field(index=True)  # 关联 dict_type.id
    parent_id: int | None = Field(default=None, index=True)
    name: str  # 展示文本
    value: str  # 存储值
    sort_order: int = Field(default=0)  # 排序 (对齐规范使用 sort_order)
    remark: str | None = None


class DictTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    name: str
    key: str
    created_at: datetime
    updated_at: datetime


class DictTypeCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    name: str
    key: str


class DictTypeUpdateRequest(DictTypeCreateRequest):
    id: int


class DictInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    type_id: int
    parent_id: int | None = None
    name: str
    value: str | None = None
    sort_order: int = 0
    remark: str | None = None
    created_at: datetime
    updated_at: datetime


class DictInfoCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    type_id: int
    parent_id: int | None = None
    name: str
    value: str | None = None
    sort_order: int = 0
    remark: str | None = None


class DictInfoUpdateRequest(DictInfoCreateRequest):
    id: int
