"""D16 清偿：agent_run_trace 补护栏版本列（一期唯一 P1 遗留）

Revision ID: 20261026_0031
Revises: 20261026_0030
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0031"
down_revision = "20261026_0030"
branch_labels = None
depends_on = None

# 设计 3.7 / 决策 D16：「每次 run 的 trace 记录实际使用的护栏版本」——一期只落了快照载荷
# guardrailsVersion（发布时点），trace 无列，安全策略「全局实时生效」无可追溯证据（核对报告
# 2.3 P1-1）。本迁移补列（可空，PG 方言 ADD COLUMN IF NOT EXISTS 幂等——0026/0027 同款教训）；
# 存量行保持 NULL（历史 run 无从判定，不回填）；新 run 由 run_service 构造时写入，编排型记 NULL。
# SQLite 开发路径不经 alembic（init_db create_all 建全列），test_migration_drift 对账列集一致。


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_run_trace ADD COLUMN IF NOT EXISTS guardrails_version VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_run_trace DROP COLUMN IF EXISTS guardrails_version")
