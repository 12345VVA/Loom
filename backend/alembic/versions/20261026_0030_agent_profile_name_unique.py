"""智能体名称唯一约束（走查反馈）：存量同名消歧 + 活跃行 partial unique 索引

Revision ID: 20261026_0030
Revises: 20261024_0029
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0030"
down_revision = "20261024_0029"
branch_labels = None
depends_on = None

# 与 uq_agent_profile_code 同构（0027）：只约束活跃行，软删后可重建同名。
# 索引名与模型 __table_args__ 一致（test_migration_drift 按名字+列集合对账）；
# CREATE INDEX IF NOT EXISTS 幂等可重放（init_db create_all 预建撞索引——0026/0027 同款教训）。
#
# 存量消歧先行：真库已有同名走查数据，不先改名索引必建失败。规则=组内保留最早一条，
# 其余 name 追加 '-'+code（code 活跃行唯一 → 消歧后全局唯一，不可能二次冲突）；
# LEFT(...,150) 对齐 name 列长。PG 方言（SQLite 开发路径不经 alembic，文件头注同源）。

_DISAMBIGUATE_SQL = """
UPDATE agent_profile p
SET name = LEFT(p.name || '-' || p.code, 150)
WHERE p.delete_time IS NULL
  AND EXISTS (
    SELECT 1 FROM agent_profile q
    WHERE q.name = p.name
      AND q.delete_time IS NULL
      AND q.id < p.id
  )
"""


def upgrade() -> None:
    op.execute(_DISAMBIGUATE_SQL)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_profile_name "
        "ON agent_profile (name) WHERE delete_time IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_agent_profile_name")
