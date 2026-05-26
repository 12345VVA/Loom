"""
工作流模型实体与 DTO。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_validator, field_serializer
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class WorkflowDefinition(BaseEntity, table=True):
    """工作流定义表"""
    __tablename__ = "workflow_definition"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    graph_json: str = Field(default="{}", max_length=100000)  # 可视化连线与配置生成的拓扑数据
    is_active: bool = Field(default=True, index=True)


class WorkflowInstance(BaseEntity, table=True):
    """工作流实例运行状态表"""
    __tablename__ = "workflow_instance"

    definition_id: int = Field(index=True)
    thread_id: str = Field(index=True, max_length=100)  # LangGraph checkpoint 隔离 thread
    status: str = Field(default="pending", index=True, max_length=50)  # pending, running, paused, success, failed
    current_node: Optional[str] = Field(default=None, max_length=100)
    state_data: str = Field(default="{}", max_length=100000)  # 运行中的上下文变量快照
    error_message: Optional[str] = Field(default=None, max_length=1000)
    celery_task_id: Optional[str] = Field(default=None, max_length=200, index=True)


class WorkflowExecutionLog(BaseEntity, table=True):
    """工作流节点执行日志"""
    __tablename__ = "workflow_execution_log"

    instance_id: int = Field(index=True)
    node_id: str = Field(index=True, max_length=100)
    node_name: str = Field(max_length=150)
    node_type: str = Field(max_length=50)
    input_data: str = Field(default="{}", max_length=100000)
    output_data: str = Field(default="{}", max_length=100000)
    latency_ms: int = Field(default=0)
    status: str = Field(default="success", max_length=50)  # success, error


# --- DTO 传输对象定义 ---

class WorkflowDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    graph_json: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class WorkflowDefinitionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    description: Optional[str] = None
    graph_json: str = "{}"
    is_active: bool = True

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class WorkflowDefinitionUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    graph_json: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class WorkflowInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    definition_id: int
    thread_id: str
    status: str
    current_node: Optional[str] = None
    state_data: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowInstanceStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    inputs: dict[str, Any] = PydanticField(default_factory=dict)


class WorkflowInstanceResumeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    instance_id: int
    user_input: Any


class WorkflowExecutionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    instance_id: int
    node_id: str
    node_name: str
    node_type: str
    input_data: str
    output_data: str
    latency_ms: int
    status: str
    created_at: datetime
