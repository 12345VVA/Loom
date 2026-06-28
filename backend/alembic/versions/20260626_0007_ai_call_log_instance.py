"""ai_model_call_log workflow_instance_id

为 ai_model_call_log 增加 workflow_instance_id 字段，使工作流评估能按 instance
精确聚合 token/cost，替代按 user_id+时间窗的近似聚合（评审报告严重问题1 长期方案）。

nullable：手动 chat 等非工作流调用为空。历史日志该字段为空，仅对新运行生效。
dev 新库由 create_all 依据模型直接生成列与索引；_ensure_sqlite_compatible_schema
为旧 dev 库补列。

Revision ID: 20260626_0007
Revises: 20260626_0006
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260626_0007"
down_revision = "20260626_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_call_log") as batch:
        batch.add_column(sa.Column("workflow_instance_id", sa.Integer(), nullable=True))
        batch.create_index("ix_ai_model_call_log_workflow_instance_id", ["workflow_instance_id"])


def downgrade() -> None:
    with op.batch_alter_table("ai_model_call_log") as batch:
        batch.drop_index("ix_ai_model_call_log_workflow_instance_id")
        batch.drop_column("workflow_instance_id")
