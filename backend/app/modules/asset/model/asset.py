"""IP 资产库模型：角色 / 场景 / 风格三表 + DTO + 模块常量。

设计基线：docs/02-业务模块/IP资产库模块设计-2026-10-22.md 3.2（契约权威版见其附录 B）。
分表而非统一 asset 表（需求 4.1）；零外键，media 关联均为逻辑关联；
不做版本管理（决策 #5，引用始终指向当前行）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, Index, Text, text
from sqlmodel import Field

from app.framework.api.naming import resolve_alias
from app.framework.models.entity import BaseEntity

# --- 模块常量 ---

ASSET_STATUS_DRAFT = "draft"
ASSET_STATUS_PUBLISHED = "published"
ASSET_STATUS_ARCHIVED = "archived"
ASSET_STATUSES = {ASSET_STATUS_DRAFT, ASSET_STATUS_PUBLISHED, ASSET_STATUS_ARCHIVED}

# 合法状态迁移边（设计 3.3）：无 published→draft 撤回边；软删独立于状态机
ASSET_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ASSET_STATUS_DRAFT: {ASSET_STATUS_PUBLISHED},
    ASSET_STATUS_PUBLISHED: {ASSET_STATUS_ARCHIVED},
    ASSET_STATUS_ARCHIVED: {ASSET_STATUS_PUBLISHED},
}

# 参考图语义角色（决策 #28）：核心仅 primary（显式化"首位首选"），angle/expression/outfit 为扩展枚举
REFERENCE_ROLES_CORE = {"primary"}

# 参考图集上限（设计细化 D2：防 JSON 无界）
MAX_REF_IMAGES = 20

# 组装协议版本（决策 #29）：拼接顺序/压缩序/去重规则/role 语义等影响指纹稳定性的
# 协议语义变更时 +1；纯 bug 修复不改版本。契约权威版见设计文档附录 B。
COMPOSER_VERSION = "1"


def _partial_unique_code_index(table: str) -> Index:
    """软删 partial unique（照抄 ai_model 的 uq_ai_model_provider_code_type 模式，AI-012 同因）：
    只约束活跃行（delete_time IS NULL），软删后可重建同 code；
    fork 副本的 code 冲突由 service 层重试唯一后缀解决。"""
    return Index(
        f"uq_asset_{table}_code",
        "code",
        unique=True,
        postgresql_where=text("delete_time IS NULL"),
        sqlite_where=text("delete_time IS NULL"),
    )


class AssetCharacter(BaseEntity, table=True):
    """角色资产：appearance_prompt 为外貌唯一拼接源（attributes 纯档案不参与拼接，决策 #11）。"""

    __tablename__ = "asset_character"
    __table_args__ = (_partial_unique_code_index("character"),)

    code: str = Field(index=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    status: str = Field(default=ASSET_STATUS_DRAFT, index=True, max_length=50)
    # 受控 dict 维度（决策 #34，设计细化 D1）：dict:asset_character_type；IP 项目维度随扩展级 asset_project 加列
    category: str | None = Field(default=None, index=True, max_length=100)

    appearance_prompt: str | None = Field(default=None, sa_column=Column(Text))
    negative_prompt: str | None = Field(default=None, sa_column=Column(Text))
    attributes: str | None = Field(default=None, sa_column=Column(Text))
    voice_prompt: str | None = Field(default=None, sa_column=Column(Text))
    # JSON: [{id, role?}]（决策 #28）；解析兼容纯 id 数组（见 service.reference.parse_ref_entries）
    ref_image_ids: str | None = Field(default=None, sa_column=Column(Text))

    preferred_profile_code: str | None = Field(default=None, max_length=100)
    preferred_size: str | None = Field(default=None, max_length=50)

    tags: str | None = Field(default=None, sa_column=Column(Text))
    cover_media_id: int | None = Field(default=None, index=True)
    # 扩展级（决策 #36）：JSON list；核心期字段已建、选择器命中提示后开
    incompatible_tags: str | None = Field(default=None, sa_column=Column(Text))
    created_by: int | None = Field(default=None, index=True)


class AssetScene(BaseEntity, table=True):
    """场景资产：结构同角色（瘦身），category 走 dict:asset_scene_type，侧重氛围属性。"""

    __tablename__ = "asset_scene"
    __table_args__ = (_partial_unique_code_index("scene"),)

    code: str = Field(index=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    status: str = Field(default=ASSET_STATUS_DRAFT, index=True, max_length=50)
    category: str | None = Field(default=None, index=True, max_length=100)

    appearance_prompt: str | None = Field(default=None, sa_column=Column(Text))
    negative_prompt: str | None = Field(default=None, sa_column=Column(Text))
    ref_image_ids: str | None = Field(default=None, sa_column=Column(Text))

    preferred_profile_code: str | None = Field(default=None, max_length=100)
    preferred_size: str | None = Field(default=None, max_length=50)

    tags: str | None = Field(default=None, sa_column=Column(Text))
    cover_media_id: int | None = Field(default=None, index=True)
    created_by: int | None = Field(default=None, index=True)


class AssetStyle(BaseEntity, table=True):
    """风格资产：结构同场景；preferred_profile_code/size 是其重心（推荐模型/参数）。"""

    __tablename__ = "asset_style"
    __table_args__ = (_partial_unique_code_index("style"),)

    code: str = Field(index=True, max_length=100)
    name: str = Field(index=True, max_length=150)
    status: str = Field(default=ASSET_STATUS_DRAFT, index=True, max_length=50)
    category: str | None = Field(default=None, index=True, max_length=100)

    appearance_prompt: str | None = Field(default=None, sa_column=Column(Text))
    negative_prompt: str | None = Field(default=None, sa_column=Column(Text))
    ref_image_ids: str | None = Field(default=None, sa_column=Column(Text))

    preferred_profile_code: str | None = Field(default=None, max_length=100)
    preferred_size: str | None = Field(default=None, max_length=50)

    tags: str | None = Field(default=None, sa_column=Column(Text))
    cover_media_id: int | None = Field(default=None, index=True)
    created_by: int | None = Field(default=None, index=True)


# --- DTO（对齐 model-schema.mdc 三件套）---
#
# Create/Update 均不含 status/created_by：状态只能经 publish/archive/restore 迁移、
# 归属由服务端写入——与 service 层剔除逻辑构成双保险（设计 3.2/3.3）。


class _AssetReadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    code: str
    name: str
    status: str
    category: str | None = None
    appearance_prompt: str | None = None
    negative_prompt: str | None = None
    ref_image_ids: str | None = None
    preferred_profile_code: str | None = None
    preferred_size: str | None = None
    tags: str | None = None
    cover_media_id: int | None = None
    # 服务端 _finalize_data 计算：ref_image_ids 中已悬空/状态异常的 media id（详情页失效标注）
    missing_media_ids: list[int] = []
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class AssetCharacterRead(_AssetReadBase):
    attributes: str | None = None
    voice_prompt: str | None = None
    incompatible_tags: str | None = None


class AssetSceneRead(_AssetReadBase):
    pass


class AssetStyleRead(_AssetReadBase):
    pass


class _AssetCreateBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    code: str
    name: str
    category: str | None = None
    appearance_prompt: str | None = None
    negative_prompt: str | None = None
    ref_image_ids: str | None = None
    preferred_profile_code: str | None = None
    preferred_size: str | None = None
    tags: str | None = None
    cover_media_id: int | None = None


class AssetCharacterCreateRequest(_AssetCreateBase):
    attributes: str | None = None
    voice_prompt: str | None = None
    incompatible_tags: str | None = None


class AssetSceneCreateRequest(_AssetCreateBase):
    pass


class AssetStyleCreateRequest(_AssetCreateBase):
    pass


class AssetCharacterUpdateRequest(AssetCharacterCreateRequest):
    id: int


class AssetSceneUpdateRequest(AssetSceneCreateRequest):
    id: int


class AssetStyleUpdateRequest(AssetStyleCreateRequest):
    id: int
