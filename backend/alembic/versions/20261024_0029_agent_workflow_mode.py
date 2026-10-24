"""智能体编排模式（E17）：execution_mode + workflow 绑定 + trace 实例回链

Revision ID: 20261024_0029
Revises: 20261024_0028
Create Date: 2026-10-24
"""

from __future__ import annotations

from alembic import op

revision = "20261024_0029"
down_revision = "20261024_0028"
branch_labels = None
depends_on = None

# 增列一律 ADD COLUMN IF NOT EXISTS 幂等可重放（真实升级路径上库可能先被 init_db 的
# create_all 预建，0026/0027 同款教训）；SQLite 开发路径不经 alembic（文件头注同源）。


def upgrade() -> None:
    op.execute("ALTER TABLE agent_profile ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(20) NOT NULL DEFAULT 'chat'")
    op.execute("ALTER TABLE agent_profile ADD COLUMN IF NOT EXISTS workflow_definition_id INTEGER")
    op.execute("ALTER TABLE agent_run_trace ADD COLUMN IF NOT EXISTS workflow_instance_id INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_run_trace DROP COLUMN IF EXISTS workflow_instance_id")
    op.execute("ALTER TABLE agent_profile DROP COLUMN IF EXISTS workflow_definition_id")
    op.execute("ALTER TABLE agent_profile DROP COLUMN IF EXISTS execution_mode")
