"""E12 工具资源版本表（二批二·S2）：双哈希当前值列 + 版本历史表

Revision ID: 20261026_0032
Revises: 20261026_0031
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0032"
down_revision = "20261026_0031"
branch_labels = None
depends_on = None

# 设计二批 3.13（E12）：
# - agent_tool_resource 增 contract_hash/meta_hash **当前值列**（sync 时随版本行同步维护，
#   资源表自身可读当前契约态）；NULL = 存量行尚未入版本体系，首次 sync 建 v1=created；
# - agent_tool_resource_version **只增不改**承载历史：双哈希 + change_kind 分类
#   （created/contract_change/meta_change/both）+ 变更时点完整形态（level/description/schema_summary）；
# - 兼容判定只看 contract_hash——meta 变更不触发运行时 fail-close（一期 is_contract_compatible
#   本就只收 parameters，天然满足；本迁移补的是变更检测与历史入册）。
# 一期 metadata_hash 混合哈希保留维护（向后兼容，不改名不改语义）。
# 幂等照 0026/0027/0029 先例（CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS）；
# 索引名与模型 __table_args__ 一致（test_migration_drift 对账）。


def upgrade() -> None:
    op.execute("ALTER TABLE agent_tool_resource ADD COLUMN IF NOT EXISTS contract_hash VARCHAR(64)")
    op.execute("ALTER TABLE agent_tool_resource ADD COLUMN IF NOT EXISTS meta_hash VARCHAR(64)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tool_resource_version (
            id SERIAL NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            delete_time TIMESTAMP WITH TIME ZONE,
            tool_name VARCHAR(150) NOT NULL,
            version INTEGER NOT NULL,
            contract_hash VARCHAR(64) NOT NULL,
            meta_hash VARCHAR(64) NOT NULL,
            change_kind VARCHAR(20) NOT NULL,
            level VARCHAR(30) NOT NULL,
            description TEXT,
            schema_summary TEXT,
            created_by INTEGER,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_tool_resource_version_tool_name ON agent_tool_resource_version (tool_name)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_tool_version "
        "ON agent_tool_resource_version (tool_name, version) WHERE delete_time IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_agent_tool_version")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_resource_version_tool_name")
    op.execute("DROP TABLE IF EXISTS agent_tool_resource_version")
    op.execute("ALTER TABLE agent_tool_resource DROP COLUMN IF EXISTS meta_hash")
    op.execute("ALTER TABLE agent_tool_resource DROP COLUMN IF EXISTS contract_hash")
