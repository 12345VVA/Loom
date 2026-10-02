"""时间列全面 timezone-aware：timestamp → timestamptz（sqlmodel 解禁前置）

模型层全部 datetime 字段已声明 DateTime(timezone=True)（BaseEntity 三字段 +
各表自有时间字段），本迁移把存量库中所有 `timestamp without time zone` 列
转为 `TIMESTAMP WITH TIME ZONE`。

USING <col> AT TIME ZONE 'UTC' 是命门：存量值为 naive UTC（datetime.utcnow
写入），必须显式按 UTC 解释——漏掉 USING 时 PG 按会话时区解释，+8 时区下
全库时间偏移 8 小时。

动态驱动（information_schema 全量扫描限定应用表），避免逐表硬编码漏列。

Revision ID: 20261002_0017
Revises: 20260920_0016
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261002_0017"
down_revision = "20260920_0016"
branch_labels = None
depends_on = None


def _naive_timestamp_columns() -> list[tuple[str, str]]:
    """列出当前库中全部 `timestamp without time zone` 列（仅应用 schema）。"""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND data_type = 'timestamp without time zone'
              AND table_name NOT IN ('alembic_version')
            ORDER BY table_name, column_name
            """
        )
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def upgrade() -> None:
    for table_name, column_name in _naive_timestamp_columns():
        op.execute(
            f'ALTER TABLE "{table_name}" '
            f'ALTER COLUMN "{column_name}" '
            f"TYPE TIMESTAMP WITH TIME ZONE "
            f'USING "{column_name}" AT TIME ZONE \'UTC\''
        )


def downgrade() -> None:
    # 回退：timestamptz → naive timestamp（按 UTC 截断 offset，数据数值不变）
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND data_type = 'timestamp with time zone'
              AND table_name NOT IN ('alembic_version')
            ORDER BY table_name, column_name
            """
        )
    ).fetchall()
    for table_name, column_name in rows:
        op.execute(
            f'ALTER TABLE "{table_name}" '
            f'ALTER COLUMN "{column_name}" '
            f"TYPE TIMESTAMP WITHOUT TIME ZONE "
            f'USING "{column_name}" AT TIME ZONE \'UTC\''
        )
