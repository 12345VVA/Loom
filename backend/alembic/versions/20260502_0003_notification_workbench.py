"""notification workbench fields

Revision ID: 20260502_0003
Revises: 20260502_0002
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_0003"
down_revision = "20260502_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_message") as batch:
        batch.add_column(sa.Column("is_recalled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("recalled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("recalled_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notification_message") as batch:
        batch.drop_column("recalled_by")
        batch.drop_column("recalled_at")
        batch.drop_column("is_recalled")
