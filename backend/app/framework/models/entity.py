"""
通用语言基类实体
"""
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class BaseEntity(SQLModel):
    """
    通用基类模型，包含 ID 和 自动时间戳
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    delete_time: Optional[datetime] = Field(default=None, index=True)
