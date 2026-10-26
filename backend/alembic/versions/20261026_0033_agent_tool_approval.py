"""E4 HITL 工具审批（二批二·S2）：审批表 + trace 状态/执行时长扩展

Revision ID: 20261026_0033
Revises: 20261026_0032
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0033"
down_revision = "20261026_0032"
branch_labels = None
depends_on = None

# 设计二批 3.5（E4）：
# - agent_tool_approval：审批行（组合唯一 (trace_id, tool_round, tool_call_id) 活跃行 partial unique
#   ——同 trace 多轮的 tool_call_id 重用不冲突）；
# - agent_run_trace.status 合法值集扩展 waiting_approval（非终态，D30——应用层枚举，无 DDL 变化）；
# - agent_run_trace.execution_ms：跨审批挂起的执行时长累计（D27——duration 不含等待）。
# 幂等照 0026-0032 先例；索引名与模型 __table_args__ 一致（test_migration_drift 对账）。


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tool_approval (
            id SERIAL NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            delete_time TIMESTAMP WITH TIME ZONE,
            session_id INTEGER NOT NULL,
            trace_id INTEGER NOT NULL,
            tool_call_group_id VARCHAR(64) NOT NULL,
            tool_round INTEGER NOT NULL,
            tool_call_id VARCHAR(150) NOT NULL,
            tool_name VARCHAR(150) NOT NULL,
            args_json TEXT,
            args_summary TEXT,
            args_hash VARCHAR(64) NOT NULL,
            snapshot_id INTEGER,
            status VARCHAR(20) NOT NULL,
            requested_by INTEGER NOT NULL,
            approver INTEGER,
            decided_at TIMESTAMP WITH TIME ZONE,
            lease_expires_at TIMESTAMP WITH TIME ZONE,
            executed_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            result_summary TEXT,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_session_id ON agent_tool_approval (session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_trace_id ON agent_tool_approval (trace_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_tool_call_group_id ON agent_tool_approval (tool_call_group_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_status ON agent_tool_approval (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_tool_approval_requested_by ON agent_tool_approval (requested_by)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_approval_call "
        "ON agent_tool_approval (trace_id, tool_round, tool_call_id) WHERE delete_time IS NULL"
    )
    op.execute("ALTER TABLE agent_run_trace ADD COLUMN IF NOT EXISTS execution_ms INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_agent_approval_call")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_requested_by")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_status")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_tool_call_group_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_trace_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_tool_approval_session_id")
    op.execute("DROP TABLE IF EXISTS agent_tool_approval")
    op.execute("ALTER TABLE agent_run_trace DROP COLUMN IF EXISTS execution_ms")
