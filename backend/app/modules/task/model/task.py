"""
系统定时任务模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity


class TaskInfo(BaseEntity, table=True):
    """任务信息表"""
    __tablename__ = "task_info"

    jobId: Optional[str] = Field(default=None, index=True)  # 对应 Midway 的 jobId
    repeatConf: Optional[str] = Field(default=None)  # 重复配置 (JSON)
    name: str = Field(index=True)  # 任务名称
    cron: Optional[str] = None  # Cron 表达式
    limit: Optional[int] = None  # 最大执行次数
    every: Optional[int] = None  # 执行间隔 (ms)
    remark: Optional[str] = None  # 备注
    status: int = Field(default=1)  # 状态 0: 停止, 1: 运行
    startDate: Optional[datetime] = None  # 开始时间
    endDate: Optional[datetime] = None  # 结束时间
    data: Optional[str] = None  # 任务参数 (JSON)
    service: Optional[str] = None  # 执行的方法路径
    type: int = Field(default=0)  # 0: 系统, 1: 用户
    nextRunTime: Optional[datetime] = None  # 下次运行时间
    taskType: int = Field(default=0)  # 任务类型 0: cron, 1: 时间间隔
    lastExecuteTime: Optional[datetime] = None  # 最后执行时间


class TaskLog(BaseEntity, table=True):
    """任务执行日志表"""
    __tablename__ = "task_log"

    taskId: int = Field(index=True)  # 关联 task_info.id
    status: int = Field(default=1)  # 0: 失败, 1: 成功
    detail: Optional[str] = None  # 结果细节或错误信息
    consumeTime: int = Field(default=0)  # 消耗时长 (ms)


class TaskInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jobId: Optional[str] = None
    name: str
    cron: Optional[str] = None
    every: Optional[int] = None
    remark: Optional[str] = None
    status: int
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    data: Optional[str] = None
    service: Optional[str] = None
    type: int
    nextRunTime: Optional[datetime] = None
    taskType: int
    lastExecuteTime: Optional[datetime] = None
    createTime: datetime = Field(alias="created_at")
    updateTime: datetime = Field(alias="updated_at")


class TaskInfoCreateRequest(BaseModel):
    name: str
    cron: Optional[str] = None
    every: Optional[int] = None
    remark: Optional[str] = None
    status: int = 1
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    data: Optional[str] = None
    service: Optional[str] = None
    type: int = 0
    taskType: int = 0


class TaskInfoUpdateRequest(TaskInfoCreateRequest):
    id: int


class TaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taskId: int
    taskName: Optional[str] = None  # 联表获取
    status: int
    detail: Optional[str] = None
    consumeTime: int
    createTime: datetime
