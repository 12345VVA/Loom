"""调用追踪审计 A3：agent_tool_call_log 加 skipped_reason 结构化列

Revision ID: 20261028_0036
Revises: 20261027_0035
Create Date: 2026-10-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261028_0036"
down_revision = "20261027_0035"
branch_labels = None
depends_on = None

# 拒绝/未执行原因此前只在 error 列文本里间接体现（「工具参数校验失败：…」前缀），
# 不可按原因统计/筛选。NULL = 正常执行（含全部历史行）。统计低频，不加索引。


def upgrade() -> None:
    op.add_column("agent_tool_call_log", sa.Column("skipped_reason", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_tool_call_log", "skipped_reason")
