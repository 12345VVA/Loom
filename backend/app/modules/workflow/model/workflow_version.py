"""工作流定义版本模型与 DTO。

纯版本表模型：WorkflowDefinition 主表不再存 graph_json，只存 current_version_id
（线上发布版指针）与 draft_version_id（草稿指针）；所有 graph_json 进本表，草稿与
已发布都是本表的行，靠 status 区分。不加外键（全项目零 foreign_key 先例），逻辑关联。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class WorkflowVersionStatus:
    """版本状态。"""

    DRAFT = "draft"  # 草稿（editor 编辑、test_node 使用）
    PUBLISHED = "published"  # 已发布（实例/eval 默认走此版）
    ARCHIVED = "archived"  # 历史归档（发布新版本后，旧 published 转入）

    ALL = (DRAFT, PUBLISHED, ARCHIVED)


class WorkflowDefinitionVersion(BaseEntity, table=True):
    """工作流定义的某个版本（草稿或已发布快照）。"""

    __tablename__ = "workflow_definition_version"

    # (definition_id, version_no) 联合唯一：防并发分配重复版本号。
    # draft 唯一性（每 definition 至多一条 draft）由 service 层事务保证，不加 status 唯一约束
    # （published/archived 会有多条）。
    __table_args__ = (
        UniqueConstraint("definition_id", "version_no", name="uq_workflow_def_version_def_no"),
    )

    definition_id: int = Field(index=True)
    version_no: int = Field(default=1)  # 定义内递增，存量迁移从 1 起
    status: str = Field(default=WorkflowVersionStatus.DRAFT, index=True, max_length=20)
    graph_json: str = Field(default="{}", max_length=100000)  # 全量图（从主表搬运）
    change_note: str | None = Field(default=None, max_length=500)  # 草稿/发布变更说明
    parent_version_id: int | None = Field(default=None, index=True)  # 版本链父版本（回滚溯源）
    published_at: datetime | None = Field(default=None)
    published_by: int | None = Field(default=None, index=True)
    user_id: int | None = Field(default=None, index=True)  # 冗余 definition owner，供 DataScope 自动过滤版本列表


# --- DTO ---


class WorkflowDefinitionVersionRead(BaseModel):
    """版本列表/分页用（不含 graph_json 大字段）。"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    definition_id: int
    version_no: int
    status: str
    change_note: str | None = None
    parent_version_id: int | None = None
    published_at: datetime | None = None
    published_by: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowDefinitionVersionDetailRead(WorkflowDefinitionVersionRead):
    """版本详情：含 graph_json，供只读预览/diff。"""

    graph_json: str


class WorkflowSaveDraftRequest(BaseModel):
    """保存草稿（editor 保存入口）。挂 definition controller。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    graph_json: str = "{}"
    code: str | None = None
    name: str | None = None
    description: str | None = None


class WorkflowPublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    change_note: str | None = None


class WorkflowRollbackRequest(BaseModel):
    """回滚：把目标历史版本复制为新草稿（默认）；immediate=True 则直接发布上线。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    target_version_id: int
    change_note: str | None = None
    immediate: bool = False


class WorkflowVersionDiffRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    version_a: int
    version_b: int
