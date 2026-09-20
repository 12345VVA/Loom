"""ai_provider 管理侧 AK/SK 凭证字段

火山方舟模型开通列表（ListModelActivations）仅支持 Access Key 鉴权（火山 V4
签名），与推理用的 Bearer API Key 相互独立。为 ai_provider 增加 admin_access_key
/ admin_secret_key 的加密存储字段与 AK 掩码，凭证沿用 secret.py 的 Fernet 加密，
不落明文。

三列均 nullable：非火山厂商以及未配置管理凭证的厂商为空。

Revision ID: 20260920_0013
Revises: 20260920_0012
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_0013"
down_revision = "20260920_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_provider") as batch:
        batch.add_column(sa.Column("admin_access_key_cipher", sa.String(), nullable=True))
        batch.add_column(sa.Column("admin_secret_key_cipher", sa.String(), nullable=True))
        batch.add_column(sa.Column("admin_access_key_mask", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_provider") as batch:
        batch.drop_column("admin_access_key_mask")
        batch.drop_column("admin_secret_key_cipher")
        batch.drop_column("admin_access_key_cipher")
