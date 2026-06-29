"""
工作流模型实体与 DTO。
"""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from pydantic import Field as PydanticField
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class WorkflowDefinition(BaseEntity, table=True):
    """工作流定义表"""

    __tablename__ = "workflow_definition"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    # 纯版本表模型：graph_json 已移至 workflow_definition_version 表（草稿/发布均存版本表）
    current_version_id: int | None = Field(default=None, index=True)  # 线上发布版指针（实例/eval 默认走此版）
    draft_version_id: int | None = Field(default=None, index=True)  # 草稿指针（editor/test_node 走此版）
    is_active: bool = Field(default=True, index=True)  # 启停开关（is_active=False 不可启动实例/发起评估）
    user_id: int | None = Field(default=None, index=True)  # 创建者，用于数据权限隔离


class WorkflowInstance(BaseEntity, table=True):
    """工作流实例运行状态表"""

    __tablename__ = "workflow_instance"

    definition_id: int = Field(index=True)
    version_id: int | None = Field(default=None, index=True)  # 本次执行所用 definition_version_id（存量 NULL）
    thread_id: str = Field(index=True, max_length=100)  # LangGraph checkpoint 隔离 thread
    status: str = Field(default="pending", index=True, max_length=50)  # pending, running, paused, success, failed
    current_node: str | None = Field(default=None, max_length=100)
    state_data: str = Field(default="{}", max_length=100000)  # 运行中的上下文变量快照
    error_message: str | None = Field(default=None, max_length=1000)
    celery_task_id: str | None = Field(default=None, max_length=200, index=True)
    user_id: int | None = Field(default=None, index=True)  # 启动者，用于数据权限隔离
    failed_node_id: str | None = Field(default=None, max_length=100)  # 失败节点ID（可观测性 + 为断点续跑铺路）


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
    # T6：full=全量输入；ref_prev=输入引用上一条 log 的 output（消除 input 冗余）
    payload_type: str = Field(default="full", max_length=20)
    diff_base_log_id: int | None = Field(default=None, index=True)
    # T8：超大载荷分离到对象存储后的引用（ref 非空时，input_data/output_data 为空）
    input_storage_ref: str | None = Field(default=None, max_length=500)
    output_storage_ref: str | None = Field(default=None, max_length=500)


# --- DTO 传输对象定义 ---


class WorkflowDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    description: str | None = None
    is_active: bool
    user_id: int | None = None
    current_version_id: int | None = None
    draft_version_id: int | None = None
    current_version_no: int | None = None  # join 版本表回填（线上发布版号）
    current_published_at: datetime | None = None  # join 回填（线上发布时间）
    draft_graph_json: str | None = None  # 仅 info 接口回填（供 editor 加载草稿）
    created_at: datetime
    updated_at: datetime

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class WorkflowDefinitionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    description: str | None = None
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
    code: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None

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
    version_id: int | None = None
    version_no: int | None = None  # join 版本表回填（展示用）
    thread_id: str
    status: str
    current_node: str | None = None
    state_data: str
    error_message: str | None = None
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowInstanceStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    inputs: dict[str, Any] = PydanticField(default_factory=dict)


class WorkflowInstanceResumeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    instance_id: int
    # 不接受 None：json.dumps(None)="null" → json.loads=None → 会走 initial_state 分支从头重跑
    user_input: str | dict[str, Any] | list[Any]

    @field_validator("user_input")
    @classmethod
    def _validate_user_input_size(cls, value: Any) -> Any:
        if len(json.dumps(value, ensure_ascii=False)) > 65536:
            raise ValueError("恢复值过大（超过 64KB）")
        return value


class WorkflowInstanceCancelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    instance_id: int


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


class NodeTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    node_id: str = PydanticField(max_length=100)
    mock_variables: dict[str, Any] = PydanticField(default_factory=dict)

    @field_validator("mock_variables")
    @classmethod
    def validate_mock_variables_size(cls, v: dict) -> dict:
        """限制 mock_variables 序列化后不超过 100KB，防止超大 payload 耗尽内存"""
        size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if size > 100 * 1024:
            raise ValueError(f"模拟变量数据过大（{size // 1024}KB），限制为 100KB 以内")
        return v


class NodeTestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    output: dict[str, Any]
    latency_ms: int
    error: str | None = None
    is_timeout: bool = False
