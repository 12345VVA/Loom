"""workflow_execution_log 节点失败原因字段

节点级执行日志此前只记 status（且唯一写入点硬编码 success），失败节点
无日志行也无错误内容。补 error_message 列后，失败节点写入 status=error
的日志行并携带可读原因（friendly_error_message 产物），执行日志抽屉
可直接展示失败原因，无需翻实例终态。

仅此一列：status 列已存在（model 注释 "success, error"），无需迁移。

Revision ID: 20260920_0014
Revises: 20260920_0013
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_0014"
down_revision = "20260920_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_execution_log") as batch:
        batch.add_column(sa.Column("error_message", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_execution_log") as batch:
        batch.drop_column("error_message")
