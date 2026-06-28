"""workflow_eval tags 字段（P1-2 数据集切片）

给 workflow_eval_test_case 和 workflow_eval_case_result 加 tags 字段，
支持按能力维度切片聚合（finalize 写 summary_payload.by_tag）。

nullable：旧数据为空，聚合时按"无 tag"跳过。dev 新库由 create_all 建列；
_ensure_sqlite_compatible_schema 为旧 sqlite 库补列。

Revision ID: 20260627_0011
Revises: 20260627_0010
Create Date: 2026-06-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260627_0011"
down_revision = "20260627_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_eval_test_case") as batch:
        batch.add_column(sa.Column("tags", sa.String(), nullable=True))
    with op.batch_alter_table("workflow_eval_case_result") as batch:
        batch.add_column(sa.Column("tags", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_eval_test_case") as batch:
        batch.drop_column("tags")
    with op.batch_alter_table("workflow_eval_case_result") as batch:
        batch.drop_column("tags")
