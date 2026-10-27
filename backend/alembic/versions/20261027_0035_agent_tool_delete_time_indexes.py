"""E4 CI 排障补丁：agent_tool_approval / agent_tool_resource_version 补 delete_time 索引

Revision ID: 20261027_0035
Revises: 20261026_0034
Create Date: 2026-10-27
"""

from __future__ import annotations

from alembic import op

revision = "20261027_0035"
down_revision = "20261026_0034"
branch_labels = None
depends_on = None

# BaseEntity.delete_time 声明了 index=True（entity.py），其余表的建表迁移均含
# ix_<table>_delete_time；0032/0033 建 agent_tool_resource_version / agent_tool_approval
# 时遗漏了这两条，alembic check 检出模型 drift（CI "Alembic 迁移链与模型 drift 校验"
# 红灯：Detected added index ix_agent_tool_approval_delete_time /
# ix_agent_tool_resource_version_delete_time）。此处补齐，幂等照 0026-0034 先例。


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_delete_time ON agent_tool_approval (delete_time)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_tool_resource_version_delete_time "
        "ON agent_tool_resource_version (delete_time)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_resource_version_delete_time")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_delete_time")
