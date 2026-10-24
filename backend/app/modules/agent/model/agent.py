"""智能体模块模型：九表 + DTO + 模块常量。

设计基线：docs/02-业务模块/智能体模块设计-2026-10-23.md 3.2（v1.5 设计冻结）。
- 发布快照三层：profile（活表）+ draft（草稿版本）+ snapshot（不可变快照）+ publish_record（当前生效指针）；
- 会话与观测：session / message / run_trace / tool_call_log；
- 工具资源层：tool_resource（SPI 收集的系统维护面，管理员启停在此表）。
- JSON 一律 Text 存储照 asset 先例（规避 SQLite/PG JSON 方言分裂）；
- 全表继承 BaseEntity（项目惯例，含 AiModelCallLog 等运行时表）；
- timezone=True 纪律：自有 datetime 字段全部带时区（sqlmodel 时区债已清偿）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField
from sqlalchemy import Column, DateTime, Index, Text, text
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity

# --- 模块常量 ---

AGENT_STATUS_DRAFT = "draft"
AGENT_STATUS_PUBLISHED = "published"
AGENT_STATUSES = {AGENT_STATUS_DRAFT, AGENT_STATUS_PUBLISHED}

# 会话运行模式（评审 P0-5：独立字段，调试隔离依据）
AGENT_RUN_MODE_DRAFT = "draft"
AGENT_RUN_MODE_PUBLISHED = "published"

# 编排模式（E17）：chat=对话型（LangGraph 运行时）；workflow=编排型（绑定已发布工作流）
AGENT_EXECUTION_MODE_CHAT = "chat"
AGENT_EXECUTION_MODE_WORKFLOW = "workflow"
AGENT_EXECUTION_MODES = {AGENT_EXECUTION_MODE_CHAT, AGENT_EXECUTION_MODE_WORKFLOW}

# run 终态机（需求 4.2 ⑤）：running 为执行中非终态；预算耗尽收尾 → completed 非 failed
AGENT_RUN_RUNNING = "running"
AGENT_RUN_COMPLETED = "completed"
AGENT_RUN_FAILED = "failed"
AGENT_RUN_CANCELLED = "cancelled"
AGENT_RUN_TIMED_OUT = "timed_out"
AGENT_RUN_TERMINAL_STATUSES = {AGENT_RUN_COMPLETED, AGENT_RUN_FAILED, AGENT_RUN_CANCELLED, AGENT_RUN_TIMED_OUT}

# 工具三级风险分级（需求 D11）：首版封闭清单全部 readonly
AGENT_TOOL_LEVEL_READONLY = "readonly"
AGENT_TOOL_LEVEL_REVERSIBLE_WRITE = "reversible_write"
AGENT_TOOL_LEVEL_DANGEROUS_WRITE = "dangerous_write"
AGENT_TOOL_LEVELS = {AGENT_TOOL_LEVEL_READONLY, AGENT_TOOL_LEVEL_REVERSIBLE_WRITE, AGENT_TOOL_LEVEL_DANGEROUS_WRITE}

# 资源来源（扩展级 MCP 预留）
AGENT_TOOL_SOURCE_BUILTIN = "builtin"
AGENT_TOOL_SOURCE_MCP = "mcp"

# 发布动作
AGENT_PUBLISH_ACTION_PUBLISH = "publish"
AGENT_PUBLISH_ACTION_ROLLBACK = "rollback"

# 消息角色
AGENT_MESSAGE_ROLES = {"user", "assistant", "tool"}


def _partial_unique_index(name: str, column: str, where: str) -> Index:
    """软删 partial unique（照 ai_model / asset 的同款模式）：
    只约束活跃行，软删后可重建同名值。"""
    return Index(
        name,
        column,
        unique=True,
        postgresql_where=text(where),
        sqlite_where=text(where),
    )


# --- 九表 ---


class AgentProfile(BaseEntity, table=True):
    """智能体定义（活表）：配置编辑面；发布后生成不可变快照供运行时消费。"""

    __tablename__ = "agent_profile"
    __table_args__ = (_partial_unique_index("uq_agent_profile_code", "code", "delete_time IS NULL"),)

    code: str = Field(index=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    description: str | None = Field(default=None, sa_column=Column(Text))
    # 绑定渠道 profile code（agent 零渠道配置，D2：渠道归 ai）
    model_profile_code: str = Field(max_length=100)
    system_prompt: str | None = Field(default=None, sa_column=Column(Text))
    # JSON 数组 of toolName（Text 存储，照 asset.ref_image_ids 先例）
    tools: str | None = Field(default=None, sa_column=Column(Text))

    temperature: float = Field(default=0.5)
    max_tokens: int = Field(default=4000)  # 单次模型生成输出上限（三层预算之一）
    max_tool_rounds: int = Field(default=12)  # 工具迭代轮次上限（评审 6 语义）
    timeout_seconds: int = Field(default=60)  # run 总时限
    enable_memory: bool = Field(default=True)  # 只控上下文注入（需求 4.4）
    # 编排模式（E17）：chat=对话型（LangGraph 运行时）；workflow=编排型（绑定已发布工作流，
    # run 分支走 workflow 实例执行——引用式绑定，执行走现行发布版，D13 冻结边界一致）
    execution_mode: str = Field(default="chat", max_length=20)
    workflow_definition_id: int | None = Field(default=None)
    enabled: bool = Field(default=True, index=True)  # 独立启停（实时运行控制，不被快照冻结）
    status: str = Field(default=AGENT_STATUS_DRAFT, index=True, max_length=50)
    created_by: int | None = Field(default=None, index=True)


class AgentProfileDraft(BaseEntity, table=True):
    """草稿版本：每次编辑同步重建 draft_json/draft_hash（评审 P1-1），仅内容变化递增版本。"""

    __tablename__ = "agent_profile_draft"

    profile_id: int = Field(index=True, unique=True)
    draft_version: int = Field(default=0)
    draft_json: str | None = Field(default=None, sa_column=Column(Text))
    draft_hash: str | None = Field(default=None, max_length=64)
    synced_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AgentProfileSnapshot(BaseEntity, table=True):
    """不可变发布快照：按 id 缓存永不失效（评审 P0-4）；冻结语义边界见 D13/D15。"""

    __tablename__ = "agent_profile_snapshot"

    profile_id: int = Field(index=True)
    version: int = Field(default=1)
    source_draft_version: int = Field(default=0)
    snapshot_hash: str = Field(index=True, max_length=64)
    agent_name: str = Field(max_length=150)
    agent_code: str = Field(max_length=100)
    snapshot_json: str | None = Field(default=None, sa_column=Column(Text))
    created_by: int | None = Field(default=None)


class AgentProfilePublishRecord(BaseEntity, table=True):
    """发布/回滚记录：is_current 指针实时点查（不缓存），partial unique 兜底并发。"""

    __tablename__ = "agent_profile_publish_record"
    __table_args__ = (
        # partial unique 条件用 boolean truthy（PG boolean 不可与 integer 比较；SQLite 同语法合法）
        _partial_unique_index("uq_agent_publish_current", "profile_id", "is_current"),
    )

    profile_id: int = Field(index=True)
    snapshot_id: int = Field(index=True)
    action: str = Field(default=AGENT_PUBLISH_ACTION_PUBLISH, max_length=20)
    is_current: bool = Field(default=False)
    rollback_from_snapshot_id: int | None = Field(default=None)
    operated_by: int | None = Field(default=None)
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AgentSession(BaseEntity, table=True):
    """会话：run_mode 独立字段支撑 draft/published 调试隔离（评审 P0-5）。"""

    __tablename__ = "agent_session"

    session_code: str = Field(index=True, max_length=100)
    profile_id: int = Field(index=True)
    user_id: int = Field(index=True)
    title: str | None = Field(default=None, max_length=200)
    run_mode: str = Field(index=True, max_length=20)
    last_message_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AgentMessage(BaseEntity, table=True):
    """消息（持久化历史，严格区别于模型上下文）：tool 角色消息携带 tool_call_id 配对。

    metadata 属性名用 meta（SQLAlchemy Declarative 保留 metadata 属性），列名仍为 metadata。
    """

    __tablename__ = "agent_message"

    session_id: int = Field(index=True)
    role: str = Field(max_length=20)
    content: str | None = Field(default=None, sa_column=Column(Text))
    name: str | None = Field(default=None, max_length=150)  # 工具名
    tool_call_id: str | None = Field(default=None, max_length=150)
    token_count: int | None = Field(default=None)
    meta: str | None = Field(default=None, sa_column=Column("metadata", Text))


class AgentRunTrace(BaseEntity, table=True):
    """run 轨迹（观测一级）：创建时 running，到终态更新为四值之一。"""

    __tablename__ = "agent_run_trace"

    profile_id: int = Field(index=True)
    run_mode: str = Field(index=True, max_length=20)
    snapshot_id: int | None = Field(default=None, index=True)
    agent_code: str = Field(default="", max_length=100)
    agent_name: str = Field(default="", max_length=150)
    session_id: int = Field(default=0, index=True)
    user_id: int = Field(index=True)
    model_calls: int = Field(default=0)
    tool_rounds: int = Field(default=0)
    tool_calls: int = Field(default=0)
    prompt_tokens: int | None = Field(default=None)
    completion_tokens: int | None = Field(default=None)
    duration_ms: int | None = Field(default=None)
    # 编排模式（E17）：workflow 型 run 的实例回链（观测跳转 workflow 模块）
    workflow_instance_id: int | None = Field(default=None)
    status: str = Field(default=AGENT_RUN_RUNNING, index=True, max_length=20)
    # 备注性错误信息（取消区分「已请求/确认终止」+ 残留清单 + 预算触发项等）
    error: str | None = Field(default=None, sa_column=Column(Text))


class AgentToolCallLog(BaseEntity, table=True):
    """工具调用明细（观测二级）：success=None 表示超时放弃后的未知残留态。"""

    __tablename__ = "agent_tool_call_log"

    trace_id: int = Field(index=True)
    tool_name: str = Field(max_length=150)
    args_summary: str | None = Field(default=None, sa_column=Column(Text))  # 脱敏截断
    result_summary: str | None = Field(default=None, sa_column=Column(Text))  # 截 200 字
    duration_ms: int | None = Field(default=None)
    success: bool | None = Field(default=None)
    error: str | None = Field(default=None, sa_column=Column(Text))


class AgentToolResource(BaseEntity, table=True):
    """工具资源层（管理面）：SPI 收集后 upsert 的系统维护字段；管理员启停（status）在此，
    sync 绝不触碰（D14 紧急禁用不被代码刷新恢复）。"""

    __tablename__ = "agent_tool_resource"
    __table_args__ = (_partial_unique_index("uq_agent_tool_resource_name", "tool_name", "delete_time IS NULL"),)

    tool_name: str = Field(index=True, max_length=150)
    display_name: str = Field(default="", max_length=150)
    description: str | None = Field(default=None, sa_column=Column(Text))
    category: str | None = Field(default=None, max_length=100)
    source_type: str = Field(default=AGENT_TOOL_SOURCE_BUILTIN, max_length=20)
    level: str = Field(default=AGENT_TOOL_LEVEL_READONLY, max_length=30)
    status: bool = Field(default=True, index=True)  # 管理员启停（实时运行控制）
    schema_summary: str | None = Field(default=None, sa_column=Column(Text))  # JSON
    prompt_metadata_json: str | None = Field(default=None, sa_column=Column(Text))  # JSON
    metadata_hash: str = Field(default="", max_length=64)
    created_by: int | None = Field(default=None)
    updated_by: int | None = Field(default=None)


# --- DTO（对齐 model-schema.mdc 三件套）---
#
# AgentProfile 的 Create/Update 不含 status/created_by/enabled：
# status 只经 publish 迁移、归属由服务端写入、enabled 走 toggleEnabled 端点
# （与 asset 状态机剔除逻辑同款双保险，设计 3.6）。


class AgentProfileCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str | None = None
    name: str
    description: str | None = None
    model_profile_code: str
    system_prompt: str | None = None
    tools: list[str] = PydField(default_factory=list)
    temperature: float = 0.5
    max_tokens: int = 4000
    max_tool_rounds: int = 12
    timeout_seconds: int = 60
    enable_memory: bool = True
    execution_mode: str = "chat"  # chat | workflow（E17 编排模式）
    workflow_definition_id: int | None = None  # execution_mode=workflow 时必填（发布校验）


class AgentProfileUpdateRequest(AgentProfileCreateRequest):
    id: int


class AgentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    description: str | None = None
    model_profile_code: str
    system_prompt: str | None = None
    tools: list[str] = PydField(default_factory=list)
    temperature: float
    max_tokens: int
    max_tool_rounds: int
    timeout_seconds: int
    enable_memory: bool
    execution_mode: str = "chat"
    workflow_definition_id: int | None = None
    enabled: bool
    status: str
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    session_code: str
    profile_id: int
    user_id: int
    title: str | None = None
    run_mode: str
    last_message_at: datetime | None = None
    created_at: datetime | None = None


class AgentMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    session_id: int
    role: str
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    token_count: int | None = None
    meta: str | None = None
    created_at: datetime | None = None


class AgentToolCallLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    trace_id: int
    tool_name: str
    args_summary: str | None = None
    result_summary: str | None = None
    duration_ms: int | None = None
    success: bool | None = None
    error: str | None = None
    created_at: datetime | None = None


class AgentRunTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    profile_id: int
    run_mode: str
    snapshot_id: int | None = None
    agent_code: str
    agent_name: str
    session_id: int
    user_id: int
    model_calls: int
    tool_rounds: int
    tool_calls: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None
    workflow_instance_id: int | None = None
    status: str
    error: str | None = None
    created_at: datetime | None = None


class AgentToolResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    tool_name: str
    display_name: str
    description: str | None = None
    category: str | None = None
    source_type: str
    level: str
    status: bool
    schema_summary: str | None = None
    prompt_metadata_json: str | None = None
    metadata_hash: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- 工具 DTO 请求 ---


class ToolToggleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    status: bool


class ProfilePublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class ProfileRollbackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    snapshot_id: int


class ProfileToggleEnabledRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    enabled: bool
