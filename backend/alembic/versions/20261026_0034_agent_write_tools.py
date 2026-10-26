"""E3 可逆写工具开放（二批二·S2 收尾）：写工具知情确认 + 写操作目标审计

Revision ID: 20261026_0034
Revises: 20261026_0033
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0034"
down_revision = "20261026_0033"
branch_labels = None
depends_on = None

# 设计二批 3.4（E3）+ 二批二字段清单（§表模型）：
# - agent_profile.write_tools_ack：创建者对绑定写工具的知情确认（D11——reversible_write
#   可发布的前置条件之一，发布校验强制；dangerous_write 仍拒绝）；
# - agent_tool_call_log.target_ref：写操作目标引用审计（"asset:3"/"media:7"；只读工具恒空）。
# 幂等照 0026-0033 先例；存量行 ack 默认 0（既有智能体未确认过写工具语义，不追溯放行）。


def upgrade() -> None:
    op.execute("ALTER TABLE agent_profile ADD COLUMN IF NOT EXISTS write_tools_ack BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE agent_tool_call_log ADD COLUMN IF NOT EXISTS target_ref VARCHAR(100)")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_tool_call_log DROP COLUMN IF EXISTS target_ref")
    op.execute("ALTER TABLE agent_profile DROP COLUMN IF EXISTS write_tools_ack")
