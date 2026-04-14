"""
字典模块模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from sqlmodel import Field, SQLModel
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
    parent_id: Optional[int] = Field(default=None, index=True)
    name: str  # 展示文本
    value: str  # 存储值
    order_num: int = Field(default=0)  # 排序
    remark: Optional[str] = None


class DictTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key: str
    createTime: datetime
    updateTime: datetime


class DictTypeCreateRequest(BaseModel):
    name: str
    key: str


class DictTypeUpdateRequest(DictTypeCreateRequest):
    id: int


class DictInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    typeId: int
    parentId: Optional[int] = None
    name: str
    value: Optional[str] = None
    orderNum: int = 0
    remark: Optional[str] = None
    createTime: datetime
    updateTime: datetime


class DictInfoCreateRequest(BaseModel):
    typeId: int
    parentId: Optional[int] = None
    name: str
    value: Optional[str] = None
    orderNum: int = 0
    remark: Optional[str] = None


class DictInfoUpdateRequest(DictInfoCreateRequest):
    id: int
