"""
通用语言基类实体
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class BaseEntity(SQLModel):
    """
    通用基类模型，包含 ID 和 自动时间戳
    """

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))
    delete_time: datetime | None = Field(default=None, index=True, sa_type=DateTime(timezone=True))
