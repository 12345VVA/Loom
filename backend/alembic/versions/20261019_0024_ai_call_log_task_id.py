"""ai_model_call_log 补 task_id（AI-030 生成任务维度成本归集）

Revision ID: 20261019_0024
Revises: 20261011_0023
Create Date: 2026-10-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261019_0024"
down_revision = "20261011_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_model_call_log", sa.Column("task_id", sa.Integer(), nullable=True))
    op.create_index("ix_ai_model_call_log_task_id", "ai_model_call_log", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_model_call_log_task_id", table_name="ai_model_call_log")
    op.drop_column("ai_model_call_log", "task_id")
