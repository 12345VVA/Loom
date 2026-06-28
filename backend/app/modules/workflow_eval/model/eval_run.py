"""工作流评估运行与用例结果模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity
from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus


class WorkflowEvalRun(BaseEntity, table=True):
    """一次批量评估运行：聚合指标 + 图快照（保证回归可比）。"""

    __tablename__ = "workflow_eval_run"

    test_set_id: int = Field(index=True)
    definition_id: int | None = Field(default=None, index=True)
    # 存量兼容：旧 run 的图快照；新 run 改用 definition_version_id，此列保留作 fallback
    graph_json_snapshot: str = Field(default="{}")
    definition_version_id: int | None = Field(default=None, index=True)  # 评估执行的精确版本（替代 snapshot）
    version_label: str | None = Field(default=None, max_length=100)  # 展示标签（仅前端显示，不再作关联键）
    status: str = Field(default=EvalRunStatus.PENDING, index=True, max_length=50)

    total: int = Field(default=0)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    errored: int = Field(default=0)

    avg_score: float = Field(default=0.0)  # 加权平均分 [0,1]
    pass_rate: float = Field(default=0.0)

    p50_latency_ms: int = Field(default=0)
    p95_latency_ms: int = Field(default=0)
    p99_latency_ms: int = Field(default=0)
    max_latency_ms: int = Field(default=0)

    total_tokens: int = Field(default=0)  # 复用 AiModelCallLog 聚合
    total_cost_micro_usd: int = Field(default=0)

    summary_payload: str | None = Field(default=None)  # JSON：完整指标 + 各评估器分布
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
    error_message: str | None = Field(default=None, max_length=1000)
    celery_task_id: str | None = Field(default=None, max_length=200, index=True)
    user_id: int | None = Field(default=None, index=True)


class WorkflowEvalCaseResult(BaseEntity, table=True):
    """单条用例的评估结果。"""

    __tablename__ = "workflow_eval_case_result"

    # (eval_run_id, case_key) 联合唯一：防同一运行出现重复 case_key 覆盖回归对比数据。
    # dev 新库由 create_all 建表时据此生成约束；已有库由 alembic 0006 补约束。
    __table_args__ = (
        UniqueConstraint("eval_run_id", "case_key", name="uq_workflow_eval_case_result_run_case_key"),
    )

    eval_run_id: int = Field(index=True)
    test_case_id: int | None = Field(default=None, index=True)
    case_key: str = Field(default="", index=True, max_length=100)  # 冗余，便于跨版本 join

    input_data: str = Field(default="{}")  # JSON：实际输入快照
    actual_output: str | None = Field(default=None)  # JSON：实际输出
    actual_output_storage_ref: str | None = Field(default=None, max_length=500)  # T8：大输出分离引用
    expected_output: str | None = Field(default=None)  # JSON

    score: float = Field(default=0.0, index=True)  # [0,1]
    passed: bool = Field(default=False, index=True)
    latency_ms: int = Field(default=0, index=True)
    token_total: int = Field(default=0)
    cost_micro_usd: int = Field(default=0)
    status: str = Field(default=CaseResultStatus.SUCCESS, index=True, max_length=50)

    evaluator_type: str = Field(default="rule_match", max_length=50)
    evaluator_detail: str | None = Field(default=None)  # JSON：各子评分、LLM 评语、命中规则
    error_message: str | None = Field(default=None, max_length=1000)
    workflow_instance_id: int | None = Field(default=None, index=True)  # 关联跑出的实例，便于回溯


# --- DTO ---


class WorkflowEvalRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    test_set_id: int
    definition_id: int | None = None
    definition_version_id: int | None = None
    version_label: str | None = None
    status: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    avg_score: float = 0.0
    pass_rate: float = 0.0
    p50_latency_ms: int = 0
    p95_latency_ms: int = 0
    p99_latency_ms: int = 0
    max_latency_ms: int = 0
    total_tokens: int = 0
    total_cost_micro_usd: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowEvalRunStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    test_set_id: int
    definition_id: int | None = None  # 缺省取测试集关联的定义
    definition_version_id: int | None = None  # 缺省取 definition 的 current_version_id
    version_label: str | None = None
    evaluator_type: str = "rule_match"


class WorkflowEvalCaseResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    eval_run_id: int
    case_key: str
    actual_output: str | None = None
    expected_output: str | None = None
    score: float
    passed: bool
    latency_ms: int
    status: str
    evaluator_type: str
    evaluator_detail: str | None = None
    error_message: str | None = None
    workflow_instance_id: int | None = None
    created_at: datetime
