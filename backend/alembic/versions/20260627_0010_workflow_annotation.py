"""workflow_annotation 人工标注表

新建 workflow_annotation 表：对评估用例结果的人工标注，用于 LLM judge 校准（Cohen's κ）。
dev 新库由 create_all 依据模型建表；本迁移为生产库建表（幂等：已存在则跳过）。

Revision ID: 20260627_0010
Revises: 20260627_0009
Create Date: 2026-06-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "20260627_0010"
down_revision = "20260627_0009"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in set(sa_inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "workflow_annotation"):
        return  # dev 库已由 create_all 建立
    op.create_table(
        "workflow_annotation",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_result_id", sa.Integer(), nullable=False),
        sa.Column("annotator_user_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=20), nullable=False, server_default="pass"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("is_gold", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_workflow_annotation_case_result_id", "workflow_annotation", ["case_result_id"])
    op.create_index("ix_workflow_annotation_annotator_user_id", "workflow_annotation", ["annotator_user_id"])
    op.create_index("ix_workflow_annotation_is_gold", "workflow_annotation", ["is_gold"])
    op.create_index("ix_workflow_annotation_delete_time", "workflow_annotation", ["delete_time"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "workflow_annotation"):
        op.drop_table("workflow_annotation")
