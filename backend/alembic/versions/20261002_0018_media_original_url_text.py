"""media_asset.original_url 改 TEXT：data URI 场景超 VARCHAR(1000)

生成失败保留 base64 preview 时 original_url 为 data URI（可达数 KB），
VARCHAR(1000) 在 PG 强制截断直接入库失败（SQLite 无长度校验掩盖）。
storage_url 保持 VARCHAR(1000)——对象存储地址不会超长。

Revision ID: 20261002_0018
Revises: 20261002_0001
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261002_0018"
down_revision = "20261002_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("media_asset", "original_url", type_=sa.Text(), existing_type=sa.String(1000))


def downgrade() -> None:
    # 回退需先截断超长值，否则 PG 拒绝收窄
    op.execute("UPDATE media_asset SET original_url = LEFT(original_url, 1000) WHERE LENGTH(original_url) > 1000")
    op.alter_column("media_asset", "original_url", type_=sa.String(1000), existing_type=sa.Text())
