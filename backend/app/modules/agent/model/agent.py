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
AGENT_RUN_WAITING_APPROVAL = "waiting_approval"  # E4：HITL 审批挂起（非终态，D27/D30 三概念分离）
AGENT_RUN_COMPLETED = "completed"
AGENT_RUN_FAILED = "failed"
AGENT_RUN_CANCELLED = "cancelled"
AGENT_RUN_TIMED_OUT = "timed_out"
AGENT_RUN_NON_TERMINAL_STATUSES = {AGENT_RUN_RUNNING, AGENT_RUN_WAITING_APPROVAL}
AGENT_RUN_TERMINAL_STATUSES = {AGENT_RUN_COMPLETED, AGENT_RUN_FAILED, AGENT_RUN_CANCELLED, AGENT_RUN_TIMED_OUT}

# 生图工具（generate_image）最低 run 时限：adapter 单次生图默认 ≤60s + 至少一轮 LLM——
# 低于此值发布与发起都拒绝（发布是第一道，发起实时道复查防发布后调低），否则计费生成被 run 超时作废
AGENT_IMAGE_TOOL_MIN_TIMEOUT = 120

# 工具三级风险分级（需求 D11）：首版封闭清单全部 readonly
AGENT_TOOL_LEVEL_READONLY = "readonly"
AGENT_TOOL_LEVEL_REVERSIBLE_WRITE = "reversible_write"
AGENT_TOOL_LEVEL_DANGEROUS_WRITE = "dangerous_write"
AGENT_TOOL_LEVELS = {AGENT_TOOL_LEVEL_READONLY, AGENT_TOOL_LEVEL_REVERSIBLE_WRITE, AGENT_TOOL_LEVEL_DANGEROUS_WRITE}

# 资源来源（扩展级 MCP 预留）
AGENT_TOOL_SOURCE_BUILTIN = "builtin"
AGENT_TOOL_SOURCE_MCP = "mcp"

# 资源版本变更分类（E12，二批 3.13：双哈希分类——兼容判定只看 contract_hash）
AGENT_TOOL_CHANGE_CREATED = "created"  # 首次入册
AGENT_TOOL_CHANGE_CONTRACT = "contract_change"  # 仅契约变（parameters/level）
AGENT_TOOL_CHANGE_META = "meta_change"  # 仅元数据变（description 等）
AGENT_TOOL_CHANGE_BOTH = "both"
AGENT_TOOL_CHANGE_KINDS = {
    AGENT_TOOL_CHANGE_CREATED,
    AGENT_TOOL_CHANGE_CONTRACT,
    AGENT_TOOL_CHANGE_META,
    AGENT_TOOL_CHANGE_BOTH,
}

# HITL 工具审批（E4，二批 3.5）：status 八值状态机
# pending → approved → executing → succeeded/failed（执行链）
# pending → rejected / expired / cancelled（决定与过期链）
AGENT_APPROVAL_PENDING = "pending"
AGENT_APPROVAL_APPROVED = "approved"
AGENT_APPROVAL_REJECTED = "rejected"
AGENT_APPROVAL_EXPIRED = "expired"
AGENT_APPROVAL_EXECUTING = "executing"
AGENT_APPROVAL_SUCCEEDED = "succeeded"
AGENT_APPROVAL_FAILED = "failed"
AGENT_APPROVAL_CANCELLED = "cancelled"
AGENT_APPROVAL_STATUSES = {
    AGENT_APPROVAL_PENDING,
    AGENT_APPROVAL_APPROVED,
    AGENT_APPROVAL_REJECTED,
    AGENT_APPROVAL_EXPIRED,
    AGENT_APPROVAL_EXECUTING,
    AGENT_APPROVAL_SUCCEEDED,
    AGENT_APPROVAL_FAILED,
    AGENT_APPROVAL_CANCELLED,
}
# 已决定（脱离 pending；approved 仍待执行）；终局（不再有任何动作）
AGENT_APPROVAL_DECIDED_STATUSES = {
    AGENT_APPROVAL_APPROVED,
    AGENT_APPROVAL_REJECTED,
    AGENT_APPROVAL_EXPIRED,
    AGENT_APPROVAL_CANCELLED,
}
AGENT_APPROVAL_TERMINAL_STATUSES = {
    AGENT_APPROVAL_SUCCEEDED,
    AGENT_APPROVAL_FAILED,
    AGENT_APPROVAL_REJECTED,
    AGENT_APPROVAL_EXPIRED,
    AGENT_APPROVAL_CANCELLED,
}

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
    __table_args__ = (
        _partial_unique_index("uq_agent_profile_code", "code", "delete_time IS NULL"),
        _partial_unique_index("uq_agent_profile_name", "name", "delete_time IS NULL"),
    )

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
    # E3：写工具知情确认——绑定 reversible_write 工具的智能体必须 ack 才可发布（D11 治理）
    write_tools_ack: bool = Field(default=False)
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
    # 本次 run 实际使用的护栏版本（D16：安全策略实时生效，trace 记版本可追溯；
    # 编排型 run 不经 LLM 护栏，记 None）
    guardrails_version: str | None = Field(default=None, max_length=20)
    status: str = Field(default=AGENT_RUN_RUNNING, index=True, max_length=20)
    # 备注性错误信息（取消区分「已请求/确认终止」+ 残留清单 + 预算触发项等）。
    # 借存语义（复核 N-2）：running/waiting 期间本列持有 f"token:{trace_token}" 取消标记
    # （stop_run 跨进程/挂起态反查用）——错误率统计须排除非终态行；终态覆写为真实错误或 None。
    error: str | None = Field(default=None, sa_column=Column(Text))
    # E4：跨审批挂起的执行时长累计（D27——duration 不含审批等待；挂起时累积，终态时 duration_ms = execution_ms + 恢复段）
    execution_ms: int = Field(default=0)


class AgentToolApproval(BaseEntity, table=True):
    """HITL 工具审批行（E4，二批 3.5）：每次需审批的 tool_call 一行，恢复处理以组为单位。

    - 组合唯一 (trace_id, tool_round, tool_call_id)（同 trace 多轮的 tool_call_id 重用不冲突）；
    - tool_call_group_id = 同一次 assistant 响应的整组标识（挂起/恢复/过期收尾的判定单元）；
    - args_json/args_hash 是审批锚点：恢复执行前 args_hash 比对（A14 漂移不可利用），
      args_json 在终局超保留期后清理（仅留摘要与 hash）；
    - 租约：进入 executing 写 lease_expires_at，到期仍 executing = 残留执行（人工核对入口）；
    - 审批占位永不入消息——挂起 AI 消息落 agent_message（meta.tool_calls），tool 结果在恢复时原子补齐。
    """

    __tablename__ = "agent_tool_approval"
    __table_args__ = (
        Index(
            "uq_agent_approval_call",
            "trace_id",
            "tool_round",
            "tool_call_id",
            unique=True,
            postgresql_where=text("delete_time IS NULL"),
            sqlite_where=text("delete_time IS NULL"),
        ),
    )

    session_id: int = Field(index=True)
    trace_id: int = Field(index=True)
    tool_call_group_id: str = Field(index=True, max_length=64)
    tool_round: int = Field(default=0)
    tool_call_id: str = Field(max_length=150)
    tool_name: str = Field(max_length=150)
    args_json: str | None = Field(default=None, sa_column=Column(Text))  # 原始 args JSON（保留期后清理）
    args_summary: str | None = Field(default=None, sa_column=Column(Text))  # 展示摘要（截断，长期保留）
    args_hash: str = Field(default="", max_length=64)
    snapshot_id: int | None = Field(default=None)
    status: str = Field(default=AGENT_APPROVAL_PENDING, index=True, max_length=20)
    requested_by: int = Field(index=True)
    approver: int | None = Field(default=None)
    decided_at: datetime | None = Field(default=None)
    lease_expires_at: datetime | None = Field(default=None)
    executed_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)  # pending 过期线（SLA）
    result_summary: str | None = Field(default=None, sa_column=Column(Text))


class AgentToolCallLog(BaseEntity, table=True):
    """工具调用明细（观测二级）：success=None 表示超时放弃后的未知残留态。"""

    __tablename__ = "agent_tool_call_log"

    trace_id: int = Field(index=True)
    tool_name: str = Field(max_length=150)
    args_summary: str | None = Field(default=None, sa_column=Column(Text))  # 脱敏截断
    result_summary: str | None = Field(default=None, sa_column=Column(Text))  # 截 200 字
    # E3：写操作目标引用（"asset:3" / "media:7"）——审计可追溯「改了哪个目标」；只读工具恒空
    target_ref: str | None = Field(default=None, max_length=100)
    duration_ms: int | None = Field(default=None)
    success: bool | None = Field(default=None)
    # 拒绝/未执行原因结构化列（调用追踪审计 A3）：cancelled/soft_failure/invalid_args/denied/
    # not_bound/contract_incompatible/budget_exhausted/error——NULL=正常执行成功；
    # 此前列只在 error 文本里间接体现，不可按原因统计
    skipped_reason: str | None = Field(default=None, max_length=30)
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
    # metadata_hash 为一期混合哈希（保留维护向后兼容）；E12 起拆双哈希当前值列（sync 随版本行同步维护）
    metadata_hash: str = Field(default="", max_length=64)
    contract_hash: str | None = Field(default=None, max_length=64)  # sha256(parameters+level)——契约态
    meta_hash: str | None = Field(default=None, max_length=64)  # sha256(description)——元数据态
    created_by: int | None = Field(default=None)
    updated_by: int | None = Field(default=None)


class AgentToolResourceVersion(BaseEntity, table=True):
    """工具资源版本表（E12，二批 3.13）：**只增不改**承载历史。

    - 版本行记录变更时点的完整形态（level/description/schema_summary + 双哈希），管理面可回放；
    - 当前值列在 agent_tool_resource.contract_hash/meta_hash（资源表自身可读当前契约态）；
    - 兼容判定只看 contract_hash——meta 变更不触发运行时 fail-close，仅入版本提示重发布；
    - NULL 当前值列 = 存量行尚未入版本体系（迁移 0032 后首次 sync 建 v1=created）。"""

    __tablename__ = "agent_tool_resource_version"
    __table_args__ = (
        Index(
            "uq_agent_tool_version",
            "tool_name",
            "version",
            unique=True,
            postgresql_where=text("delete_time IS NULL"),
            sqlite_where=text("delete_time IS NULL"),
        ),
    )

    tool_name: str = Field(index=True, max_length=150)
    version: int = Field(default=1)
    contract_hash: str = Field(default="", max_length=64)
    meta_hash: str = Field(default="", max_length=64)
    change_kind: str = Field(default=AGENT_TOOL_CHANGE_CREATED, max_length=20)
    level: str = Field(default=AGENT_TOOL_LEVEL_READONLY, max_length=30)
    description: str | None = Field(default=None, sa_column=Column(Text))  # 本版本时点值（meta 回放）
    schema_summary: str | None = Field(default=None, sa_column=Column(Text))  # 本版本时点值（契约回放）
    created_by: int | None = Field(default=None)


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
    write_tools_ack: bool = False  # E3：写工具知情确认（绑定 reversible_write 工具时发布校验强制）


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
    write_tools_ack: bool = False
    status: str
    # 「有未发布修改」（脏标记）：仅发布行有意义——当前草稿的发布 hash ≠ 生效快照 hash；
    # 由 service._finalize_data 出口计算（Read 默认 False，draft 行恒 False）
    has_pending_changes: bool = False
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
    target_ref: str | None = None
    duration_ms: int | None = None
    success: bool | None = None
    error: str | None = None
    # 未执行原因（cancelled/soft_failure/invalid_args/...；NULL=正常执行）——复核 2026-10-29：
    # Read DTO 未声明该字段时 Pydantic 出口静默丢弃，前端「取消/拒绝原因」标签永不生效
    skipped_reason: str | None = None
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
    guardrails_version: str | None = None
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
    contract_hash: str | None = None
    meta_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentToolResourceVersionRead(BaseModel):
    """资源版本行（E12 管理面回放：变更时点形态 + 双哈希分类）。"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    tool_name: str
    version: int
    contract_hash: str
    meta_hash: str
    change_kind: str
    level: str
    description: str | None = None
    schema_summary: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None


# --- 工具 DTO 请求 ---


class ToolToggleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    status: bool


class AgentToolApprovalRead(BaseModel):
    """审批行（管理审批面）：args_json 不出列（治理——面上看摘要与 hash，args 原文仅执行链内部消费）。"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    session_id: int
    trace_id: int
    tool_call_group_id: str
    tool_round: int
    tool_call_id: str
    tool_name: str
    args_summary: str | None = None
    args_hash: str
    snapshot_id: int | None = None
    status: str
    requested_by: int
    approver: int | None = None
    decided_at: datetime | None = None
    lease_expires_at: datetime | None = None
    executed_at: datetime | None = None
    expires_at: datetime | None = None
    result_summary: str | None = None
    created_at: datetime | None = None


class ApprovalDecideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    action: str  # approve / reject


class ApprovalReconcileRequest(BaseModel):
    """executing 租约到期残留的人工核对处置（A25）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    outcome: str  # succeeded / failed
    note: str | None = None


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
