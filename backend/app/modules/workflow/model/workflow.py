"""
工作流模型实体与 DTO。
"""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from pydantic import Field as PydanticField
from sqlalchemy import Index
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

    # 实例列表按定义 + 时间查询（名称与 database.INDEX_DEFINITIONS 一致，见 ai_model_call_log 注释）
    __table_args__ = (Index("ix_workflow_instance_definition_id_created_at", "definition_id", "created_at"),)

    definition_id: int = Field(index=True)
    version_id: int | None = Field(default=None, index=True)  # 本次执行所用 definition_version_id（存量 NULL）
    thread_id: str = Field(index=True, max_length=100)  # LangGraph checkpoint 隔离 thread
    status: str = Field(default="pending", index=True, max_length=50)  # pending, running, paused, success, failed
    current_node: str | None = Field(default=None, max_length=100)
    # 运行中的上下文变量快照（T8 超阈值载荷分离到对象存储后，此处存空串并置状态快照引用）
    state_data: str = Field(default="{}", max_length=100000)
    # T8：state_data 超阈值时落对象存储的引用（ref 非空时 state_data 为空串，读取需 resolve_payload 还原）
    state_data_ref: str | None = Field(default=None, max_length=500)
    error_message: str | None = Field(default=None, max_length=1000)
    celery_task_id: str | None = Field(default=None, max_length=200, index=True)
    user_id: int | None = Field(default=None, index=True)  # 启动者，用于数据权限隔离
    failed_node_id: str | None = Field(default=None, max_length=100)  # 失败节点ID（可观测性 + 为断点续跑铺路）
    # 运行类型：production 正式 | trial 编辑器试运行（草稿版）| eval 批量评估。
    # 测试实例的产物打同款标记、失败不发通知、列表默认过滤（见 _notify_workflow_failure / QueryConfig field_eq）
    run_type: str = Field(default="production", index=True, max_length=20)
    eval_run_id: int | None = Field(
        default=None, index=True
    )  # eval 专有：回溯 WorkflowEvalRun（trial/production 为 NULL）

    @property
    def is_test(self) -> bool:
        """便捷判断：非正式运行（trial/eval）。派生自 run_type，不落库。"""
        return self.run_type != "production"


class WorkflowExecutionLog(BaseEntity, table=True):
    """工作流节点执行日志"""

    __tablename__ = "workflow_execution_log"

    # 节点日志按实例 + 时间排序/分页（名称与 database.INDEX_DEFINITIONS 一致）
    __table_args__ = (Index("ix_workflow_execution_log_instance_id_created_at", "instance_id", "created_at"),)

    instance_id: int = Field(index=True)
    node_id: str = Field(index=True, max_length=100)
    node_name: str = Field(max_length=150)
    node_type: str = Field(max_length=50)
    input_data: str = Field(default="{}", max_length=100000)
    output_data: str = Field(default="{}", max_length=100000)
    latency_ms: int = Field(default=0)
    status: str = Field(default="success", max_length=50)  # success, error
    # 节点失败原因（status=error 时写入），供日志抽屉直接展示，无需翻实例终态
    error_message: str | None = Field(default=None, max_length=1000)
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

    # code 可选：前端不传时由 service._before_add 自动生成（WF+日期+序列，唯一）
    code: str | None = None
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
    failed_node_id: str | None = None  # 失败节点ID（透传给前端定位失败节点）
    run_type: str = "production"  # production | trial | eval（前端徽标 + 默认列表过滤）
    eval_run_id: int | None = None
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    total_tokens: int | None = None  # 本次运行 LLM 累计 token（按 instance 聚合 AiModelCallLog）
    cost_usd: float | None = None  # 本次运行累计成本（USD）


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
    error_message: str | None = None
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
    instance_id: int | None = None  # 落库的测试实例 ID（run_type='test_node'，可跳转运行记录页）
