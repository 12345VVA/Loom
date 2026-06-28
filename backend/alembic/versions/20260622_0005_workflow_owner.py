"""workflow owner

为 workflow_definition 与 workflow_instance 增加创建者字段 user_id，
用于工作流模块的数据权限隔离（修复审查报告 S1 IDOR）。

Revision ID: 20260622_0005
Revises: 20260506_0004
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260622_0005"
down_revision = "20260506_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_definition") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_workflow_definition_user_id", ["user_id"])

    with op.batch_alter_table("workflow_instance") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_workflow_instance_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("workflow_instance") as batch:
        batch.drop_index("ix_workflow_instance_user_id")
        batch.drop_column("user_id")

    with op.batch_alter_table("workflow_definition") as batch:
        batch.drop_index("ix_workflow_definition_user_id")
        batch.drop_column("user_id")
