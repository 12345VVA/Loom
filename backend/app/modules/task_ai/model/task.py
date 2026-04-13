"""
Task 模块任务模型
"""
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(SQLModel, table=True):
    """任务表"""

    __tablename__ = "tasks"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: int = Field(index=True, foreign_key="sys_user.id")
    prompt: str = Field(index=True)
    task_type: str = Field(default="text_generation")
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)
    result: Optional[str] = None
    error: Optional[str] = None
    progress: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    celery_task_id: Optional[str] = None


class TaskCreate(SQLModel):
    """创建任务请求"""

    prompt: str
    task_type: str = "text_generation"
    user_id: Optional[int] = None


class TaskUpdate(SQLModel):
    """更新任务请求"""

    id: str
    prompt: str
    task_type: str = "text_generation"


class TaskDeleteRequest(BaseModel):
    """任务删除请求"""

    ids: list[str] = PydanticField(default_factory=list)


class TaskCancelRequest(BaseModel):
    """任务取消请求"""

    id: str


class TaskRead(SQLModel):
    """任务响应"""

    id: str
    user_id: int
    prompt: str
    task_type: str
    status: TaskStatus
    result: Optional[str] = None
    error: Optional[str] = None
    progress: float
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int] = PydanticField(default_factory=dict)
