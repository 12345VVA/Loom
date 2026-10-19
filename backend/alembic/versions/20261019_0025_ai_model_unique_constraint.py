"""ai_model 加 (provider_id, code, model_type) 部分唯一索引（AI-012）

改成**部分唯一索引**（``WHERE delete_time IS NULL``）而非表级唯一约束，原因有二：

1. 正确性：普通唯一约束把软删行也算进键，导致「软删后重建同 code」永久失败——管理端
   列表看不到软删行（Session 级软删不变量过滤），创建却报「已存在」，只能改 code；
2. 部署安全：普通约束要求**同键组内所有行**（含历史软删行）都唯一。存量库里
   「软删行 + 活跃行同键」很常见（旧版唯一校验看不到软删行，允许重复创建），
   只软删活跃重复行的做法无法清干净，约束创建会失败（已实测复现）。

部分索引天然只约束活跃行，因此本迁移**不需要**任何去重 UPDATE。

若本地曾升级过本迁移的旧版本（表级唯一约束），需重跑一次：
``alembic downgrade 20261019_0024 && alembic upgrade head``

Revision ID: 20261019_0025
Revises: 20261019_0024
Create Date: 2026-10-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261019_0025"
down_revision = "20261019_0024"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_ai_model_provider_code_type"
_ACTIVE_ONLY = sa.text("delete_time IS NULL")


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "ai_model",
        ["provider_id", "code", "model_type"],
        unique=True,
        postgresql_where=_ACTIVE_ONLY,
        sqlite_where=_ACTIVE_ONLY,
    )


def downgrade() -> None:
    # 兼容两种历史形态：旧版本建的是表级唯一约束（PG 上有约束名），新版本建的是部分唯一索引
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE ai_model DROP CONSTRAINT IF EXISTS {_INDEX_NAME}")
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
