"""ai_runtime_invocation task_id / cc_keys 字段

为 ai_runtime_invocation 增加 task_id 与 cc_keys：cancel 异步任务时按 task 精确
定位 running invocation 并释放并发计数（governance_service.release_by_task），
cc_keys 持久化 acquire 时的 Redis key 集合（JSON），worker 被 terminate 后仍可
精确 decr，不受规则后续增删影响。

两列均 nullable：同步调用（无 task_id）与无并发规则的 invocation 为空，
仅对 release 路径生效。dev 新库由 create_all 依据模型直接生成列与索引；
_ensure_sqlite_compatible_schema / _ensure_indexes 为旧 dev 库补列补索引。

Revision ID: 20260920_0012
Revises: 20260627_0011
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_0012"
down_revision = "20260627_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_runtime_invocation") as batch:
        batch.add_column(sa.Column("task_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("cc_keys", sa.String(length=500), nullable=True))
        batch.create_index("ix_ai_runtime_invocation_task_id", ["task_id"])


def downgrade() -> None:
    with op.batch_alter_table("ai_runtime_invocation") as batch:
        batch.drop_index("ix_ai_runtime_invocation_task_id")
        batch.drop_column("cc_keys")
        batch.drop_column("task_id")
