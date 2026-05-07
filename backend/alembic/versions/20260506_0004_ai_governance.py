"""ai governance

Revision ID: 20260506_0004
Revises: 20260502_0003
Create Date: 2026-05-06 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "20260506_0004"
down_revision = "20260502_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_call_log") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("cost_micro_usd", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("currency", sa.String(length=20), nullable=False, server_default="USD"))
        batch.create_index("ix_ai_model_call_log_user_id", ["user_id"])

    op.create_table(
        "ai_governance_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("scope_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("period", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("max_requests", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("max_cost_micro_usd", sa.Integer(), nullable=True),
        sa.Column("max_concurrent", sa.Integer(), nullable=True),
        sa.Column("mode", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("notify_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_governance_rule_code", "ai_governance_rule", ["code"], unique=True)
    op.create_index("ix_ai_governance_rule_scope_type", "ai_governance_rule", ["scope_type"])
    op.create_index("ix_ai_governance_rule_user_id", "ai_governance_rule", ["user_id"])
    op.create_index("ix_ai_governance_rule_profile_id", "ai_governance_rule", ["profile_id"])

    op.create_table(
        "ai_governance_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("metric", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("rule_id", "user_id", "profile_id", "model_id", "provider_id", "event_type", "metric"):
        op.create_index(f"ix_ai_governance_event_{col}", "ai_governance_event", [col])

    op.create_table(
        "ai_runtime_invocation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
        sa.Column("invocation_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_runtime_invocation_invocation_id", "ai_runtime_invocation", ["invocation_id"], unique=True)
    op.create_index("ix_ai_runtime_invocation_status", "ai_runtime_invocation", ["status"])


def downgrade() -> None:
    op.drop_table("ai_runtime_invocation")
    op.drop_table("ai_governance_event")
    op.drop_table("ai_governance_rule")
    with op.batch_alter_table("ai_model_call_log") as batch:
        batch.drop_index("ix_ai_model_call_log_user_id")
        batch.drop_column("currency")
        batch.drop_column("cost_micro_usd")
        batch.drop_column("user_id")
