"""
通知模块模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity


class NotificationMessage(BaseEntity, table=True):
    __tablename__ = "notification_message"

    title: str = Field(index=True, max_length=200)
    content: str
    message_type: str = Field(default="business", index=True)
    level: str = Field(default="info", index=True)
    source_module: Optional[str] = Field(default=None, index=True)
    business_key: Optional[str] = Field(default=None, index=True)
    link_url: Optional[str] = None
    send_status: str = Field(default="sent", index=True)
    scheduled_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    sender_id: Optional[int] = Field(default=None, index=True)
    is_recalled: bool = Field(default=False, index=True)
    recalled_at: Optional[datetime] = None
    recalled_by: Optional[int] = Field(default=None, index=True)


class NotificationRecipient(BaseEntity, table=True):
    __tablename__ = "notification_recipient"

    message_id: int = Field(index=True)
    user_id: int = Field(index=True)
    role_id: Optional[int] = Field(default=None, index=True)
    department_id: Optional[int] = Field(default=None, index=True)
    tenant_id: Optional[int] = Field(default=None, index=True)
    is_read: bool = Field(default=False, index=True)
    read_time: Optional[datetime] = None
    is_archived: bool = Field(default=False, index=True)
    is_deleted: bool = Field(default=False, index=True)


class NotificationTemplate(BaseEntity, table=True):
    __tablename__ = "notification_template"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    title_template: str
    content_template: str
    default_level: str = Field(default="info")
    default_link_url: Optional[str] = None
    is_active: bool = Field(default=True, index=True)


class NotificationRule(BaseEntity, table=True):
    __tablename__ = "notification_rule"

    code: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(index=True, max_length=100)
    users: Optional[str] = None
    roles: Optional[str] = None
    departments: Optional[str] = None
    tenants: Optional[str] = None
    include_child_departments: bool = True
    all_admins: bool = False
    condition: Optional[str] = None
    is_active: bool = True


class AudienceRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    users: list[int] = PydanticField(default_factory=list)
    roles: list[int | str] = PydanticField(default_factory=list)
    departments: list[int] = PydanticField(default_factory=list)
    tenants: list[int] = PydanticField(default_factory=list)
    include_child_departments: bool = True
    all_admins: bool = False
    condition: Optional[str] = None


class NotificationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    title: str
    content: str
    message_type: str
    level: str
    source_module: Optional[str] = None
    business_key: Optional[str] = None
    link_url: Optional[str] = None
    send_status: str
    scheduled_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    sender_id: Optional[int] = None
    is_recalled: bool = False
    recalled_at: Optional[datetime] = None
    recalled_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class NotificationMessageCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    title: str
    content: str
    message_type: str = "business"
    level: str = "info"
    source_module: Optional[str] = None
    business_key: Optional[str] = None
    link_url: Optional[str] = None
    send_status: str = "sent"
    scheduled_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    sender_id: Optional[int] = None
    is_recalled: bool = False
    recalled_at: Optional[datetime] = None
    recalled_by: Optional[int] = None
    audience: AudienceRule = PydanticField(default_factory=AudienceRule)


class NotificationMessageUpdateRequest(NotificationMessageCreateRequest):
    id: int


class NotificationMessageSendRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    title: str
    content: str
    message_type: str = "business"
    level: str = "info"
    source_module: Optional[str] = None
    business_key: Optional[str] = None
    link_url: Optional[str] = None
    audience: AudienceRule = PydanticField(default_factory=AudienceRule)


class NotificationRecipientPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    audience: AudienceRule = PydanticField(default_factory=AudienceRule)


class NotificationTemplatePreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    context: dict = PydanticField(default_factory=dict)


class NotificationTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    title_template: str
    content_template: str
    default_level: str
    default_link_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    title_template: str
    content_template: str
    default_level: str = "info"
    default_link_url: Optional[str] = None
    is_active: bool = True


class NotificationTemplateUpdateRequest(NotificationTemplateCreateRequest):
    id: int


class NotificationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    users: Optional[str] = None
    roles: Optional[str] = None
    departments: Optional[str] = None
    tenants: Optional[str] = None
    include_child_departments: bool
    all_admins: bool
    condition: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationRuleCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    users: Optional[str] = None
    roles: Optional[str] = None
    departments: Optional[str] = None
    tenants: Optional[str] = None
    include_child_departments: bool = True
    all_admins: bool = False
    condition: Optional[str] = None
    is_active: bool = True


class NotificationRuleUpdateRequest(NotificationRuleCreateRequest):
    id: int
