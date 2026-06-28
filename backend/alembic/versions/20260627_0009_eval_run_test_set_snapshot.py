"""workflow_eval_run test_set_snapshot

为 WorkflowEvalRun 加 test_set_snapshot 字段：发起评估时复制用例集快照，
保证历史 run 可复现（不受后续用例改动影响）。

nullable：旧 run 为空，load_eval_context 回退查当前用例。
dev 新库由 create_all 依据模型生成列；_ensure_sqlite_compatible_schema 为旧库补列。

Revision ID: 20260627_0009
Revises: 20260626_0008
Create Date: 2026-06-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260627_0009"
down_revision = "20260626_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_eval_run") as batch:
        batch.add_column(sa.Column("test_set_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_eval_run") as batch:
        batch.drop_column("test_set_snapshot")
