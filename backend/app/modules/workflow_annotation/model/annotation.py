"""工作流评估结果人工标注模型 + Cohen's κ judge 校准。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class WorkflowAnnotation(BaseEntity, table=True):
    """对某条评估用例结果（WorkflowEvalCaseResult）的人工标注。

    一个 case_result 可有多条标注（多标注者）；is_gold 标记用于 judge 校准的金标准。
    """

    __tablename__ = "workflow_annotation"

    case_result_id: int = Field(index=True)
    annotator_user_id: int | None = Field(default=None, index=True)
    label: str = Field(default="pass", max_length=20)  # pass | fail
    score: float | None = Field(default=None)  # 可选 0-1 分（细粒度）
    reason: str | None = Field(default=None, max_length=500)
    is_gold: bool = Field(default=False, index=True)


# --- DTO ---


class WorkflowAnnotationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    case_result_id: int
    annotator_user_id: int | None = None
    label: str
    score: float | None = None
    reason: str | None = None
    is_gold: bool = False
    created_at: datetime
    updated_at: datetime


class WorkflowAnnotationCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    case_result_id: int
    label: str = "pass"
    score: float | None = None
    reason: str | None = None
    is_gold: bool = False


class WorkflowAnnotationUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    label: str | None = None
    score: float | None = None
    reason: str | None = None
    is_gold: bool | None = None


class KappaRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    eval_run_id: int
