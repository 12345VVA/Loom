"""工作流长期记忆模型与 DTO（Workflow Memory）。

以工作流为一级命名空间的跨实例持久化共享上下文：记忆只能被产生它的
工作流的后续实例访问，工作流之间完全隔离；本期无用户维度（纯共享）。
逻辑命名空间两级：workflow/{definition_id}/{memory_env}——definition_id
是逻辑工作流 ID（跨版本稳定），memory_env 隔离生产/测试。
设计文档：docs/工作流长期记忆节点设计方案-2026-10-07.md（v5.2）。

唯一性两条 partial unique index（软删行不参与判定，删除后同 content 可重新写入）：
- uq_mem_key：有 key 行按 (definition_id, memory_env, memory_key) 唯一——
  同 key 仅一行现行，key upsert 语义的数据库兜底；
- uq_mem_hash：无 key 行按 (definition_id, memory_env, content_hash) 唯一——
  精确去重兜底。仅限 memory_key IS NULL：有 key 行的唯一性由 key 承担，
  key upsert 更新 content 至与别行相同不违约（key/hash 正交）。
不加外键（全项目零 foreign_key 先例），definition_id 逻辑关联。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, Text, text
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class MemoryEnv:
    """记忆环境（与 run_type 职责分离：env 管隔离域，run_type 管溯源）。"""

    PRODUCTION = "production"
    TEST = "test"


class MemoryType:
    """记忆类型。preference 在纯共享模型下是「工作流级偏好口径」，非任何用户偏好。"""

    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    EXPERIENCE = "experience"

    ALL = (FACT, PREFERENCE, DECISION, EXPERIENCE)


class SourceRunType:
    """记忆产生渠道（纯溯源，不参与召回资格——那是 memory_env 的职责）。"""

    ADMIN = "admin"


# partial unique index 的软删行排除条件（SQLite 走 sqlite_where，PG 走 postgresql_where）
_MEM_KEY_WHERE = text("memory_key IS NOT NULL AND delete_time IS NULL")
_MEM_HASH_WHERE = text("memory_key IS NULL AND delete_time IS NULL")


class WorkflowMemory(BaseEntity, table=True):
    """工作流长期记忆（工作流一级命名空间，共享级）。"""

    __tablename__ = "workflow_memory"

    __table_args__ = (
        # 唯一索引列序 definition_id 在前：匹配查询模式与选择性（唯一性不受列序影响）
        Index(
            "uq_mem_key",
            "definition_id",
            "memory_env",
            "memory_key",
            unique=True,
            sqlite_where=_MEM_KEY_WHERE,
            postgresql_where=_MEM_KEY_WHERE,
        ),
        Index(
            "uq_mem_hash",
            "definition_id",
            "memory_env",
            "content_hash",
            unique=True,
            sqlite_where=_MEM_HASH_WHERE,
            postgresql_where=_MEM_HASH_WHERE,
        ),
        # 主检索路径复合索引（候选集查询：归属 + 环境 + 活跃行）
        Index("ix_workflow_memory_definition_env", "definition_id", "memory_env", "delete_time"),
    )

    # --- 归属（运行时上下文推导，绝不来自 variables/节点 config——安全边界）---
    definition_id: int = Field(index=True)

    # --- 环境 ---
    memory_env: str = Field(default=MemoryEnv.PRODUCTION, max_length=20)

    # --- 身份与内容 ---
    memory_type: str = Field(default=MemoryType.FACT, max_length=20)
    memory_key: str | None = Field(default=None, index=True, max_length=200)  # 业务身份（如 customer:42:quote_policy）
    content: str = Field(max_length=4000)
    content_hash: str = Field(max_length=64)  # SHA-256 hex，normalize_for_hash 后取值；仅无 key 行参与唯一约束
    tags: str = Field(default="[]", max_length=2000)  # JSON list[str]，召回粗滤维度

    # --- 向量（三态由 embedding_space + embedding 组合表达，见设计 §4.5）---
    # 显式 Text：无界 VARCHAR 语义不明（实施前澄清 #8）
    embedding: str | None = Field(default=None, sa_column=Column(Text))  # JSON float[]
    # "model:dimension" 形态专属 ready 行；生成失败落裸 model code（无维度段，检索侧跳过精排）
    embedding_space: str | None = Field(default=None, max_length=150)

    # --- 溯源（纯记录；key upsert 的 UPDATE 会刷新 source_* = 「当前内容来源」语义）---
    source_instance_id: int | None = Field(default=None, index=True)  # 实例删除后保留悬空 id（管理页标注）
    source_node_id: str | None = Field(default=None, max_length=100)
    source_run_type: str | None = Field(default=None, max_length=20)  # production|trial|test_node|admin|NULL
    created_by_user_id: int | None = Field(default=None)  # 最初创建者（恒不变）
    updated_by_user_id: int | None = Field(default=None)  # 最后写入者（INSERT=创建者，key upsert 刷新）

    # --- 容量保护排序依据之一：COALESCE(last_accessed_at, updated_at, created_at) ---
    last_accessed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    # 二期预留：subject_user_id（工作流内用户私有记忆）——本期不建列，
    # 引入时加列 + 两条索引 + memoryTarget 配置，迁移成本低。


# --- DTO（管理页四动作 add/delete/page/info，无 update——修正走删旧+新增或 key upsert）---


class WorkflowMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    definition_id: int
    definition_name: str | None = None  # join 定义表回填（展示用）
    memory_env: str
    memory_type: str
    memory_key: str | None = None
    content: str
    tags: str
    # 不透出 embedding 原始向量（大字段无展示价值）与 content_hash（内部字段）；
    # embedding_space 透出供管理页展示三态（NULL/裸 code/model:dimension）
    embedding_space: str | None = None
    source_instance_id: int | None = None
    source_node_id: str | None = None
    source_run_type: str | None = None
    created_by_user_id: int | None = None
    updated_by_user_id: int | None = None
    last_accessed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # 响应期计算字段（不落库）：凭据模式命中列表（service enrich 时对 content 跑
    # detect_credential_patterns）——管理页凭据警告列数据源（设计 §9.3/§11）
    credential_hits: list[str] | None = None


class WorkflowMemoryAddRequest(BaseModel):
    """管理页手工新增。memory_env 恒 production（不可选）；source_run_type 记 admin。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    content: str
    memory_type: str = MemoryType.FACT
    memory_key: str | None = PydanticField(default=None, max_length=200)
    tags: list[str] = PydanticField(default_factory=list)
    # 可选：填则同步向量化（成功 ready / 失败落裸 code 失败态）；不填落 NULL 走关键词回退
    embedding_profile_code: str | None = None

    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        if v not in MemoryType.ALL:
            raise ValueError(f"memory_type 仅支持 {'/'.join(MemoryType.ALL)}")
        return v

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("记忆内容不能为空")
        if len(v) > 4000:
            raise ValueError("记忆内容不能超过 4000 字符")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags_size(cls, v: list[str]) -> list[str]:
        import json

        if len(json.dumps(v, ensure_ascii=False)) > 2000:
            raise ValueError("tags 序列化后不能超过 2000 字符")
        return v
