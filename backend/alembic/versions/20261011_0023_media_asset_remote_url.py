"""media_asset.remote_url 云端镜像直链（WFI-3a 双轨存储）

Revision ID: 20261011_0023
Revises: 20261007_0022
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261011_0023"
down_revision = "20261007_0022"
branch_labels = None
depends_on = None

# TOS/S3 异步镜像成功后回写的公网可访问 URL（公开读直链或预签名）。
# nullable、无索引：按 storage_url 反查已走索引，remote_url 仅读展示/下游消费。


def upgrade() -> None:
    op.add_column(
        "media_asset",
        sa.Column("remote_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media_asset", "remote_url")
