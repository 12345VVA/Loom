"""
系统配置与字典模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity




class SysParam(BaseEntity, table=True):
    """系统参数配置"""

    __tablename__ = "sys_param"

    name: str = Field(index=True)
    key_name: str = Field(index=True, unique=True)
    data: Optional[str] = None
    data_type: int = Field(default=0)  # 0: 字符串 1: 富文本 2: 文件
    remark: Optional[str] = None



class SysLog(BaseEntity, table=True):
    """审计日志表"""
    __tablename__ = "sys_log"

    user_id: Optional[int] = Field(default=None, index=True)
    action: str = Field(index=True)  # 接口路径
    method: str = Field(index=True)  # 请求方法
    params: Optional[str] = None  # 请求参数 (JSON)
    ip: Optional[str] = None
    ip_addr: Optional[str] = None
    status: int = Field(default=1)  # 0: 失败, 1: 成功
    message: Optional[str] = None  # 结果细节


class SysLoginLog(BaseEntity, table=True):
    """登录日志表"""

    __tablename__ = "sys_login_log"

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


class SysSecurityLog(BaseEntity, table=True):
    """安全审计日志表 - 用于记录用户、角色、权限相关的敏感操作"""

    __tablename__ = "sys_security_log"

    # 操作者信息
    operator_id: int = Field(index=True)  # 操作者用户ID
    operator_name: str = Field(index=True)  # 操作者用户名
    operator_ip: Optional[str] = None  # 操作者IP地址

    # 操作对象信息
    target_type: str = Field(index=True)  # 操作对象类型: user/role/menu/department
    target_id: Optional[int] = Field(default=None, index=True)  # 操作对象ID
    target_name: Optional[str] = None  # 操作对象名称（用于快速查询）

    # 操作详情
    operation: str = Field(index=True)  # 操作类型: create/update/delete/reset_password/assign_role/grant_permission
    module: str = Field(index=True)  # 所属模块: user/role/menu/department
    resource_path: Optional[str] = None  # 资源路径

    # 变更数据（JSON格式）
    old_value: Optional[str] = None  # 变更前的数据（脱敏后）
    new_value: Optional[str] = None  # 变更后的数据（脱敏后）
    diff_data: Optional[str] = None  # 变更差异（JSON格式）

    # 审计信息
    business_type: Optional[str] = None  # 业务类型（用于分类查询）
    request_id: Optional[str] = Field(default=None, index=True)  # 关联请求ID
    status: int = Field(default=1, index=True)  # 操作状态: 0=失败, 1=成功
    error_message: Optional[str] = None  # 失败时的错误信息

    # 审计备注（操作者填写的理由）
    remark: Optional[str] = None




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


class SysSecurityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operatorId: int
    operatorName: str
    operatorIp: Optional[str] = None
    targetType: str
    targetId: Optional[int] = None
    targetName: Optional[str] = None
    operation: str
    module: str
    resourcePath: Optional[str] = None
    oldValue: Optional[str] = None
    newValue: Optional[str] = None
    diffData: Optional[str] = None
    businessType: Optional[str] = None
    requestId: Optional[str] = None
    status: int
    errorMessage: Optional[str] = None
    remark: Optional[str] = None
    createTime: datetime
    updateTime: datetime


class SysSecurityLogCreateRequest(BaseModel):
    operatorId: int
    operatorName: str
    operatorIp: Optional[str] = None
    targetType: str
    targetId: Optional[int] = None
    targetName: Optional[str] = None
    operation: str
    module: str
    resourcePath: Optional[str] = None
    oldValue: Optional[str] = None
    newValue: Optional[str] = None
    diffData: Optional[str] = None
    businessType: Optional[str] = None
    requestId: Optional[str] = None
    status: int = 1
    errorMessage: Optional[str] = None
    remark: Optional[str] = None
