"""工作流评估测试集与用例模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class WorkflowTestSet(BaseEntity, table=True):
    """测试集：一组用例 + 关联的工作流定义快照。"""

    __tablename__ = "workflow_eval_test_set"

    name: str = Field(index=True, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    # 关联工作流定义；可空以便通用测试集（跨定义复用）
    definition_id: int | None = Field(default=None, index=True)
    items_count: int = Field(default=0)  # 冗余计数，列表展示用
    tags: str | None = Field(default=None)  # JSON 数组字符串
    user_id: int | None = Field(default=None, index=True)  # 数据权限


class WorkflowTestCase(BaseEntity, table=True):
    """测试用例：单条输入 + 期望 + 评估器配置。"""

    __tablename__ = "workflow_eval_test_case"

    test_set_id: int = Field(index=True)
    case_key: str = Field(index=True, max_length=100)  # 集内唯一，回归对比按此对齐
    input_data: str = Field(default="{}")  # JSON：工作流输入载荷
    expected_output: str | None = Field(default=None)  # JSON：期望输出（供 rule_match）
    expected_text: str | None = Field(default=None, max_length=2000)  # 简化期望文本
    evaluator_config: str | None = Field(default=None)  # JSON：该用例专属评估器配置
    weight: float = Field(default=1.0)
    sort_order: int = Field(default=0)
    tags: str | None = Field(default=None)  # JSON 数组字符串：能力维度标签，用于切片聚合（P1-2）


# --- DTO ---


class WorkflowTestSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    name: str
    description: str | None = None
    definition_id: int | None = None
    items_count: int = 0
    tags: str | None = None
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowTestSetCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    name: str
    description: str | None = None
    definition_id: int | None = None
    tags: str | None = None


class WorkflowTestSetUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    name: str | None = None
    description: str | None = None
    definition_id: int | None = None
    tags: str | None = None


class WorkflowTestCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    test_set_id: int
    case_key: str
    input_data: str
    expected_output: str | None = None
    expected_text: str | None = None
    evaluator_config: str | None = None
    weight: float = 1.0
    sort_order: int = 0
    tags: str | None = None


class WorkflowTestCaseImportItem(BaseModel):
    """批量导入用例的单条结构（前端传 dict，后端序列化为 JSON 字符串存库）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    case_key: str
    input_data: dict[str, Any] | None = None
    expected_output: dict[str, Any] | str | None = None
    expected_text: str | None = None
    evaluator_config: dict[str, Any] | None = None
    tags: list[str] | None = None
    weight: float = 1.0


class WorkflowTestCaseImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    test_set_id: int
    cases: list[WorkflowTestCaseImportItem]


class WorkflowTestCaseCreateRequest(BaseModel):
    """单条用例新增（input_data/evaluator_config 为 JSON 字符串，由前端 stringify）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    test_set_id: int
    case_key: str
    input_data: str | None = None
    expected_output: str | None = None
    expected_text: str | None = None
    evaluator_config: str | None = None
    weight: float = 1.0
    sort_order: int = 0
    tags: str | None = None


class WorkflowTestCaseUpdateRequest(BaseModel):
    """单条用例编辑（不允许改 test_set_id，避免 items_count 失衡）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    case_key: str | None = None
    input_data: str | None = None
    expected_output: str | None = None
    expected_text: str | None = None
    evaluator_config: str | None = None
    weight: float | None = None
    sort_order: int | None = None
    tags: str | None = None
