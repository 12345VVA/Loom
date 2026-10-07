"""ai_model_profile 表添加 custom_config 字段，支持模型参数自定义与覆盖

Revision ID: 20261007_0021
Revises: 20261005_0020
Create Date: 2026-10-07
"""

from __future__ import annotations

from alembic import op

revision = "20261007_0021"
down_revision = "20261005_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_add_column_if_missing("ai_model_profile", "custom_config", "TEXT")
    else:
        op.execute("ALTER TABLE ai_model_profile ADD COLUMN IF NOT EXISTS custom_config TEXT")


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.execute("ALTER TABLE ai_model_profile DROP COLUMN IF EXISTS custom_config")


def _sqlite_add_column_if_missing(table: str, column: str, ddl: str) -> None:
    """SQLite 无 IF NOT EXISTS：查 PRAGMA table_info 已有列则跳过。"""
    bind = op.get_bind()
    cols = [row[1] for row in bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        bind.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
