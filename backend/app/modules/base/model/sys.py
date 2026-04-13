"""
系统配置与字典模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field, SQLModel




class SysParam(SQLModel, table=True):
    """系统参数配置"""

    __tablename__ = "sys_param"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    key_name: str = Field(index=True, unique=True)
    data: Optional[str] = None
    data_type: int = Field(default=0)  # 0: 字符串 1: 富文本 2: 文件
    remark: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)



class SysLog(SQLModel, table=True):
    """审计日志表"""
    __tablename__ = "sys_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    action: str = Field(index=True)  # 接口路径
    method: str = Field(index=True)  # 请求方法
    params: Optional[str] = None  # 请求参数 (JSON)
    ip: Optional[str] = None
    ip_addr: Optional[str] = None
    status: int = Field(default=1)  # 0: 失败, 1: 成功
    message: Optional[str] = None  # 结果细节
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SysLoginLog(SQLModel, table=True):
    """登录日志表"""

    __tablename__ = "sys_login_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    name: Optional[str] = None
    account: Optional[str] = Field(default=None, index=True)
    login_type: str = Field(default="password", index=True)
    status: int = Field(default=1)
    ip: Optional[str] = None
    risk_hit: int = Field(default=0)
    reason: Optional[str] = None
    client_type: Optional[str] = None
    device_id: Optional[str] = None
    source_system: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)




class SysParamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    keyName: str
    data: Optional[str] = None
    dataType: int = 0
    remark: Optional[str] = None
    createTime: datetime
    updateTime: datetime


class SysParamCreateRequest(BaseModel):
    name: str
    keyName: str
    data: Optional[str] = None
    dataType: int = 0
    remark: Optional[str] = None


class SysParamUpdateRequest(SysParamCreateRequest):
    id: int


class SysLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    userId: Optional[int] = None
    name: Optional[str] = None
    action: str
    method: str
    params: Optional[str] = None
    ip: Optional[str] = None
    status: int
    message: Optional[str] = None
    createTime: datetime


class SysLogKeepRequest(BaseModel):
    value: int = PydanticField(default=7, ge=1, le=10000)


class SysLoginLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    userId: Optional[int] = None
    name: Optional[str] = None
    account: Optional[str] = None
    loginType: str
    status: int
    ip: Optional[str] = None
    riskHit: int = 0
    reason: Optional[str] = None
    clientType: Optional[str] = None
    deviceId: Optional[str] = None
    sourceSystem: Optional[str] = None
    userAgent: Optional[str] = None
    createTime: datetime
    updateTime: datetime


class SysLoginLogCreateRequest(BaseModel):
    userId: Optional[int] = None
    name: Optional[str] = None
    account: Optional[str] = None
    loginType: str = "password"
    status: int = 1
    ip: Optional[str] = None
    riskHit: int = 0
    reason: Optional[str] = None
    clientType: Optional[str] = None
    deviceId: Optional[str] = None
    sourceSystem: Optional[str] = None
    userAgent: Optional[str] = None


class SysLoginLogUpdateRequest(SysLoginLogCreateRequest):
    id: int
