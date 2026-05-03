"""
AI 模型管理实体与 DTO。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_validator
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


class AiProvider(BaseEntity, table=True):
    __tablename__ = "ai_provider"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    adapter: str = Field(default="openai-compatible", index=True, max_length=50)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key_cipher: Optional[str] = None
    api_key_mask: Optional[str] = Field(default=None, max_length=100)
    extra_config: Optional[str] = None
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModel(BaseEntity, table=True):
    __tablename__ = "ai_model"

    provider_id: int = Field(index=True)
    code: str = Field(index=True, max_length=150)
    name: str = Field(index=True, max_length=150)
    model_type: str = Field(default="chat", index=True, max_length=50)
    capabilities: Optional[str] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    pricing_config: Optional[str] = None
    default_config: Optional[str] = None
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModelProfile(BaseEntity, table=True):
    __tablename__ = "ai_model_profile"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    model_id: int = Field(index=True)
    scenario: str = Field(default="default", index=True, max_length=100)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[str] = None
    tools_config: Optional[str] = None
    timeout: Optional[int] = None
    retry_count: int = Field(default=0)
    retry_delay_seconds: int = Field(default=0)
    fallback_profile_id: Optional[int] = Field(default=None, index=True)
    is_default: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)


class AiModelCallLog(BaseEntity, table=True):
    __tablename__ = "ai_model_call_log"

    provider_id: Optional[int] = Field(default=None, index=True)
    model_id: Optional[int] = Field(default=None, index=True)
    profile_id: Optional[int] = Field(default=None, index=True)
    scenario: Optional[str] = Field(default=None, index=True, max_length=100)
    model_type: str = Field(default="chat", index=True, max_length=50)
    status: str = Field(default="success", index=True, max_length=50)
    latency_ms: int = Field(default=0)
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    error_message: Optional[str] = Field(default=None, max_length=500)
    request_id: Optional[str] = Field(default=None, index=True, max_length=100)


class AiGenerationTask(BaseEntity, table=True):
    __tablename__ = "ai_generation_task"

    task_type: str = Field(default="chat", index=True, max_length=50)
    scenario: str = Field(default="default", index=True, max_length=100)
    profile_code: Optional[str] = Field(default=None, index=True, max_length=100)
    status: str = Field(default="pending", index=True, max_length=50)
    progress: int = Field(default=0)
    request_payload: Optional[str] = None
    result_payload: Optional[str] = None
    error_message: Optional[str] = Field(default=None, max_length=1000)
    celery_task_id: Optional[str] = Field(default=None, index=True, max_length=100)
    created_by: Optional[int] = Field(default=None, index=True)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retry_count: int = Field(default=0)


class AiModelCallLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    provider_id: Optional[int] = None
    provider_name: Optional[str] = None
    model_id: Optional[int] = None
    model_name: Optional[str] = None
    profile_id: Optional[int] = None
    profile_name: Optional[str] = None
    scenario: Optional[str] = None
    model_type: str
    status: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_message: Optional[str] = None
    request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AiProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    adapter: str
    base_url: Optional[str] = None
    api_key_mask: Optional[str] = None
    has_api_key: bool = False
    extra_config: Optional[str] = None
    is_active: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class AiProviderCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    adapter: str = "openai-compatible"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Optional[str] = None
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


class AiProviderTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiCatalogImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    provider_code: str
    overwrite_models: bool = True


class AiModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    provider_id: int
    provider_name: Optional[str] = None
    code: str
    name: str
    model_type: str
    capabilities: Optional[str] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    pricing_config: Optional[str] = None
    default_config: Optional[str] = None
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
    capabilities: Optional[str] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    pricing_config: Optional[str] = None
    default_config: Optional[str] = None
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


class AiModelProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    model_id: int
    model_name: Optional[str] = None
    model_type: Optional[str] = None
    provider_name: Optional[str] = None
    scenario: str
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[str] = None
    tools_config: Optional[str] = None
    timeout: Optional[int] = None
    retry_count: int = 0
    retry_delay_seconds: int = 0
    fallback_profile_id: Optional[int] = None
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
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[str] = None
    tools_config: Optional[str] = None
    timeout: Optional[int] = None
    retry_count: int = 0
    retry_delay_seconds: int = 0
    fallback_profile_id: Optional[int] = None
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
    description: Optional[str] = None
    schema_: dict[str, Any] = PydanticField(alias="schema")
    strict: bool = True


class AiResponseFormatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    type: str = "text"
    json_schema: Optional[AiResponseJsonSchema | dict[str, Any]] = None


class AiChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    messages: list[AiRuntimeMessage]
    options: dict[str, Any] = PydanticField(default_factory=dict)
    response_format: Optional[AiResponseFormatRequest | dict[str, Any]] = None


class AiEmbeddingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    input: str | list[str]
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiImageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    prompt: str
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiRerankRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    query: str
    documents: list[str]
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiAudioRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    input: str
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiVideoRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    scenario: str = "default"
    profile_code: Optional[str] = None
    prompt: str
    options: dict[str, Any] = PydanticField(default_factory=dict)


class AiGenerationTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    task_type: str
    scenario: str
    profile_code: Optional[str] = None
    status: str
    progress: int = 0
    request_payload: Optional[str] = None
    result_payload: Optional[str] = None
    error_message: Optional[str] = None
    celery_task_id: Optional[str] = None
    created_by: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class AiTaskSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    task_type: str = "chat"
    scenario: str = "default"
    profile_code: Optional[str] = None
    payload: dict[str, Any]


class AiTaskActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int


class AiProfileTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    prompt: str = "你好，请用一句话介绍你自己。"
