"""
AI 模型管理实体与 DTO。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity

AI_ADAPTERS = {
    "openai-compatible",
    "ollama",
    "gemini",
    "claude",
    "deepseek",
    "volcengine-ark",
    "bailian",
    "hunyuan",
    "qianfan",
    "zhipu",
    "minimax",
    "mimo",
}
AI_MODEL_TYPES = {"chat", "embedding", "image", "audio", "video", "rerank"}
AI_GOVERNANCE_SCOPE_TYPES = {"global", "user", "profile"}
AI_GOVERNANCE_PERIODS = {"minute", "day", "month"}
AI_GOVERNANCE_MODES = {"enforce", "observe"}
AI_GOVERNANCE_EVENT_TYPES = {"allowed", "blocked", "warn", "breach"}
AI_INVOCATION_STATUSES = {"running", "success", "error", "blocked"}


class AiProvider(BaseEntity, table=True):
    __tablename__ = "ai_provider"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    adapter: str = Field(default="openai-compatible", index=True, max_length=50)
    base_url: str | None = Field(default=None, max_length=500)
    api_key_cipher: str | None = None
    api_key_mask: str | None = Field(default=None, max_length=100)
    extra_config: str | None = None
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModel(BaseEntity, table=True):
    __tablename__ = "ai_model"

    provider_id: int = Field(index=True)
    code: str = Field(index=True, max_length=150)
    name: str = Field(index=True, max_length=150)
    model_type: str = Field(default="chat", index=True, max_length=50)
    capabilities: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    pricing_config: str | None = None
    default_config: str | None = None
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModelProfile(BaseEntity, table=True):
    __tablename__ = "ai_model_profile"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    model_id: int = Field(index=True)
    scenario: str = Field(default="default", index=True, max_length=100)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    response_format: str | None = None
    tools_config: str | None = None
    timeout: int | None = None
    retry_count: int = Field(default=0)
    retry_delay_seconds: int = Field(default=0)
    fallback_profile_id: int | None = Field(default=None, index=True)
    is_default: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModelCallLog(BaseEntity, table=True):
    __tablename__ = "ai_model_call_log"

    provider_id: int | None = Field(default=None, index=True)
    model_id: int | None = Field(default=None, index=True)
    profile_id: int | None = Field(default=None, index=True)
    user_id: int | None = Field(default=None, index=True)
    scenario: str | None = Field(default=None, index=True, max_length=100)
    model_type: str = Field(default="chat", index=True, max_length=50)
    status: str = Field(default="success", index=True, max_length=50)
    latency_ms: int = Field(default=0)
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    cost_micro_usd: int = Field(default=0)
    currency: str = Field(default="USD", max_length=20)
    error_message: str | None = Field(default=None, max_length=500)
    request_id: str | None = Field(default=None, index=True, max_length=100)
    # 工作流实例关联：评估按 instance 精确聚合 token/cost（手动 chat 等非工作流调用为空）
    workflow_instance_id: int | None = Field(default=None, index=True)


class AiGenerationTask(BaseEntity, table=True):
    __tablename__ = "ai_generation_task"

    task_type: str = Field(default="chat", index=True, max_length=50)
    scenario: str = Field(default="default", index=True, max_length=100)
    profile_code: str | None = Field(default=None, index=True, max_length=100)
    status: str = Field(default="pending", index=True, max_length=50)
    progress: int = Field(default=0)
    request_payload: str | None = None
    result_payload: str | None = None
    error_message: str | None = Field(default=None, max_length=1000)
    celery_task_id: str | None = Field(default=None, index=True, max_length=100)
    created_by: int | None = Field(default=None, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int = Field(default=0)


class AiGovernanceRule(BaseEntity, table=True):
    __tablename__ = "ai_governance_rule"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    scope_type: str = Field(default="global", index=True, max_length=50)
    user_id: int | None = Field(default=None, index=True)
    profile_id: int | None = Field(default=None, index=True)
    period: str = Field(default="day", index=True, max_length=50)
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost_micro_usd: int | None = None
    max_concurrent: int | None = None
    mode: str = Field(default="enforce", index=True, max_length=50)
    notify_enabled: bool = Field(default=True, index=True)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiGovernanceEvent(BaseEntity, table=True):
    __tablename__ = "ai_governance_event"

    rule_id: int | None = Field(default=None, index=True)
    user_id: int | None = Field(default=None, index=True)
    profile_id: int | None = Field(default=None, index=True)
    model_id: int | None = Field(default=None, index=True)
    provider_id: int | None = Field(default=None, index=True)
    event_type: str = Field(default="allowed", index=True, max_length=50)
    metric: str = Field(default="request", index=True, max_length=50)
    current_value: int = Field(default=0)
    limit_value: int = Field(default=0)
    window_start: datetime | None = Field(default=None, index=True)
    window_end: datetime | None = Field(default=None, index=True)
    message: str | None = Field(default=None, max_length=1000)
    notified: bool = Field(default=False, index=True)


class AiRuntimeInvocation(BaseEntity, table=True):
    __tablename__ = "ai_runtime_invocation"

    invocation_id: str = Field(index=True, unique=True, max_length=100)
    user_id: int | None = Field(default=None, index=True)
    profile_id: int | None = Field(default=None, index=True)
    model_id: int | None = Field(default=None, index=True)
    provider_id: int | None = Field(default=None, index=True)
    status: str = Field(default="running", index=True, max_length=50)
    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
    # 关联的 AI 生成任务：cancel 时据此精确释放并发计数，避免按 user 误杀同用户其他任务
    task_id: int | None = Field(default=None, index=True)
    # 持久化本次 acquire 的并发计数 Redis key（JSON），worker 被 terminate 后仍可据此精确 decr，
    # 且与 acquire 时的 key 集合一致，不受规则后续增删影响
    cc_keys: str | None = Field(default=None, max_length=500)


class AiModelCallLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    provider_id: int | None = None
    provider_name: str | None = None
    model_id: int | None = None
    model_name: str | None = None
    profile_id: int | None = None
    profile_name: str | None = None
    user_id: int | None = None
    username: str | None = None
    scenario: str | None = None
    model_type: str
    status: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_micro_usd: int = 0
    cost_usd: float = 0
    currency: str = "USD"
    error_message: str | None = None
    request_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AiProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    adapter: str
    base_url: str | None = None
    api_key_mask: str | None = None
    has_api_key: bool = False
    extra_config: str | None = None
    is_active: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class AiProviderCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    adapter: str = "openai-compatible"
    base_url: str | None = None
    api_key: str | None = None
    extra_config: str | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, value: str) -> str:
        if value not in AI_ADAPTERS:
            raise ValueError("不支持的模型厂商适配器")
        return value


class AiProviderUpdateRequest(AiProviderCreateRequest):
    id: int
    # 放开继承自 Create 的必填字段，支持部分更新（如只改 is_active/api_key）
    code: str | None = None
    name: str | None = None


class AiProviderTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiCatalogImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    provider_code: str
    overwrite_models: bool = True


class AiProviderSyncModelsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    provider_id: int
    provider_name: str | None = None
    code: str
    name: str
    model_type: str
    capabilities: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    pricing_config: str | None = None
    default_config: str | None = None
    is_active: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class AiModelCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    provider_id: int
    code: str
    name: str
    model_type: str = "chat"
    capabilities: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    pricing_config: str | None = None
    default_config: str | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("model_type")
    @classmethod
    def validate_model_type(cls, value: str) -> str:
        if value not in AI_MODEL_TYPES:
            raise ValueError("不支持的模型类型")
        return value


class AiModelUpdateRequest(AiModelCreateRequest):
    id: int
    # 放开继承自 Create 的必填字段，支持部分更新（如只改 is_active/pricing_config）
    provider_id: int | None = None
    code: str | None = None
    name: str | None = None


class AiModelProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    model_id: int
    model_name: str | None = None
    model_type: str | None = None
    model_code: str | None = None
    model_capabilities: str | None = None
    provider_name: str | None = None
    provider_code: str | None = None
    provider_adapter: str | None = None
    model_default_config: str | None = None
    scenario: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    response_format: str | None = None
    tools_config: str | None = None
    timeout: int | None = None
    retry_count: int = 0
    retry_delay_seconds: int = 0
    fallback_profile_id: int | None = None
    is_default: bool
    is_active: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class AiModelProfileCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    model_id: int
    scenario: str = "default"
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    response_format: str | None = None
    tools_config: str | None = None
    timeout: int | None = None
    retry_count: int = 0
    retry_delay_seconds: int = 0
    fallback_profile_id: int | None = None
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0

    @field_validator("model_id", mode="before")
    @classmethod
    def normalize_model_id(cls, value: Any) -> Any:
        if isinstance(value, list):
            return value[0] if value else None
        return value


class AiModelProfileUpdateRequest(AiModelProfileCreateRequest):
    id: int
    # 放开继承自 Create 的必填字段，支持部分更新（如切 is_default/is_active、调 temperature）
    code: str | None = None
    name: str | None = None
    model_id: int | None = None


class AiProfileActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiRuntimeMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    role: str
    content: str


class AiResponseJsonSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    name: str
    description: str | None = None
    schema_: dict[str, Any] = PydanticField(alias="schema")
    strict: bool = True


class AiResponseFormatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    type: str = "text"
    json_schema: AiResponseJsonSchema | dict[str, Any] | None = None


class AiChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    messages: list[AiRuntimeMessage]
    options: dict[str, Any] = PydanticField(default_factory=dict)
    response_format: AiResponseFormatRequest | dict[str, Any] | None = None
    skip_masking: bool = False


class AiEmbeddingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    input: str | list[str]
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiImageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    prompt: str
    image: str | list[str] | None = None
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiRerankRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    query: str
    documents: list[str]
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiAudioRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    input: str
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiVideoRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: str | None = None
    prompt: str
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiGenerationTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    task_type: str
    scenario: str
    profile_code: str | None = None
    status: str
    progress: int = 0
    request_payload: str | None = None
    result_payload: str | None = None
    error_message: str | None = None
    celery_task_id: str | None = None
    created_by: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class AiTaskSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    task_type: str = "chat"
    scenario: str = "default"
    profile_code: str | None = None
    payload: dict[str, Any]


class AiTaskActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiProfileTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    prompt: str = "你好，请用一句话介绍你自己。"


class AiGovernanceRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    scope_type: str
    user_id: int | None = None
    username: str | None = None
    profile_id: int | None = None
    profile_name: str | None = None
    period: str
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost_micro_usd: int | None = None
    max_concurrent: int | None = None
    mode: str
    notify_enabled: bool
    is_active: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class AiGovernanceRuleCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    scope_type: str = "global"
    user_id: int | None = None
    profile_id: int | None = None
    period: str = "day"
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost_micro_usd: int | None = None
    max_concurrent: int | None = None
    mode: str = "enforce"
    notify_enabled: bool = True
    is_active: bool = True
    sort_order: int = 0

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, value: str) -> str:
        if value not in AI_GOVERNANCE_SCOPE_TYPES:
            raise ValueError("不支持的治理范围")
        return value

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        if value not in AI_GOVERNANCE_PERIODS:
            raise ValueError("不支持的统计周期")
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in AI_GOVERNANCE_MODES:
            raise ValueError("不支持的治理模式")
        return value


class AiGovernanceRuleUpdateRequest(AiGovernanceRuleCreateRequest):
    id: int
    # 放开继承自 Create 的必填 code/name，支持部分更新（启停已有 toggle 旁路，其余字段也可行内编辑）
    code: str | None = None
    name: str | None = None


class AiGovernanceRuleActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiGovernanceRuleMatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    user_id: int | None = None
    profile_id: int | None = None


class AiGovernanceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    rule_id: int | None = None
    rule_name: str | None = None
    user_id: int | None = None
    username: str | None = None
    profile_id: int | None = None
    profile_name: str | None = None
    model_id: int | None = None
    model_name: str | None = None
    provider_id: int | None = None
    provider_name: str | None = None
    event_type: str
    metric: str
    current_value: int = 0
    limit_value: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    message: str | None = None
    notified: bool = False
    created_at: datetime
    updated_at: datetime


class AiGovernanceStatsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    days: int = 14


class AiCallStatsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    days: int = 14
    group_by: str = "day"
