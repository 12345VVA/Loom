"""
系统定时任务模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity
from app.framework.api.naming import resolve_alias


class TaskInfo(BaseEntity, table=True):
    """任务信息表"""
    __tablename__ = "task_info"

    job_id: Optional[str] = Field(default=None, index=True)  # 对应 Midway 的 jobId
    repeat_conf: Optional[str] = Field(default=None)  # 重复配置 (JSON)
    name: str = Field(index=True)  # 任务名称
    cron: Optional[str] = None  # Cron 表达式
    limit: Optional[int] = None  # 最大执行次数
    every: Optional[int] = None  # 执行间隔 (ms)
    remark: Optional[str] = None  # 备注
    status: int = Field(default=1)  # 状态 0: 停止, 1: 运行
    start_date: Optional[datetime] = None  # 开始时间
    end_date: Optional[datetime] = None  # 结束时间
    data: Optional[str] = None  # 任务参数 (JSON)
    service: Optional[str] = None  # 执行的方法路径
    type: int = Field(default=0)  # 0: 系统, 1: 用户
    next_run_time: Optional[datetime] = None  # 下次运行时间
    task_type: int = Field(default=0)  # 任务类型 0: cron, 1: 时间间隔
    last_execute_time: Optional[datetime] = None  # 最后执行时间
    notify_enabled: bool = Field(default=False)
    notify_on_success: bool = Field(default=False)
    notify_on_failure: bool = Field(default=True)
    notify_on_timeout: bool = Field(default=True)
    notify_recipients: Optional[str] = None
    notify_template_code: Optional[str] = None
    notify_timeout_ms: int = Field(default=30000)


class TaskLog(BaseEntity, table=True):
    """任务执行日志表"""
    __tablename__ = "task_log"

    task_id: int = Field(index=True)  # 关联 task_info.id
    status: int = Field(default=1)  # 0: 失败, 1: 成功
    detail: Optional[str] = None  # 结果细节或错误信息
    consume_time: int = Field(default=0)  # 消耗时长 (ms)


class TaskInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    job_id: Optional[str] = None
    name: str
    cron: Optional[str] = None
    every: Optional[int] = None
    remark: Optional[str] = None
    status: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    data: Optional[str] = None
    service: Optional[str] = None
    type: int
    next_run_time: Optional[datetime] = None
    task_type: int
    last_execute_time: Optional[datetime] = None
    notify_enabled: bool = False
    notify_on_success: bool = False
    notify_on_failure: bool = True
    notify_on_timeout: bool = True
    notify_recipients: Optional[str] = None
    notify_template_code: Optional[str] = None
    notify_timeout_ms: int = 30000
    created_at: datetime
    updated_at: datetime


class TaskInfoCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    name: str
    cron: Optional[str] = None
    every: Optional[int] = None
    remark: Optional[str] = None
    status: int = 1
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    data: Optional[str] = None
    service: Optional[str] = None
    type: int = 0
    task_type: int = 0
    notify_enabled: bool = False
    notify_on_success: bool = False
    notify_on_failure: bool = True
    notify_on_timeout: bool = True
    notify_recipients: Optional[str] = None
    notify_template_code: Optional[str] = None
    notify_timeout_ms: int = 30000


class TaskInfoUpdateRequest(TaskInfoCreateRequest):
    id: int


class TaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    task_id: int
    task_name: Optional[str] = None  # 联表获取
    status: int
    detail: Optional[str] = None
    consume_time: int
    created_at: datetime
