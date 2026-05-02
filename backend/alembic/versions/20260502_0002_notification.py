"""add notification module

Revision ID: 20260502_0002
Revises: 20260502_0001
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_0002"
down_revision = "20260502_0001"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "notification_message",
        *_base_columns(),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="system"),
        sa.Column("level", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("source_module", sa.String(length=64), nullable=True),
        sa.Column("business_key", sa.String(length=128), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("send_status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("expired_at", sa.DateTime(), nullable=True),
        sa.Column("sender_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_notification_message_business_key", "notification_message", ["business_key"])
    op.create_index("ix_notification_message_type", "notification_message", ["message_type"])

    op.create_table(
        "notification_recipient",
        *_base_columns(),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_time", sa.DateTime(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_notification_recipient_message_id", "notification_recipient", ["message_id"])
    op.create_index("ix_notification_recipient_user_id", "notification_recipient", ["user_id"])

    op.create_table(
        "notification_template",
        *_base_columns(),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("title_template", sa.String(length=200), nullable=False),
        sa.Column("content_template", sa.Text(), nullable=False),
        sa.Column("default_level", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("default_link_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_notification_template_code", "notification_template", ["code"], unique=True)

    op.create_table(
        "notification_rule",
        *_base_columns(),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("users", sa.JSON(), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=True),
        sa.Column("departments", sa.JSON(), nullable=True),
        sa.Column("tenants", sa.JSON(), nullable=True),
        sa.Column("include_child_departments", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("all_admins", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("condition", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_notification_rule_code", "notification_rule", ["code"], unique=True)

    with op.batch_alter_table("task_info") as batch:
        batch.add_column(sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("notify_on_success", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("notify_on_failure", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("notify_on_timeout", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("notify_recipients", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("notify_template_code", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("notify_timeout_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("task_info") as batch:
        batch.drop_column("notify_timeout_ms")
        batch.drop_column("notify_template_code")
        batch.drop_column("notify_recipients")
        batch.drop_column("notify_on_timeout")
        batch.drop_column("notify_on_failure")
        batch.drop_column("notify_on_success")
        batch.drop_column("notify_enabled")

    op.drop_index("ix_notification_rule_code", table_name="notification_rule")
    op.drop_table("notification_rule")
    op.drop_index("ix_notification_template_code", table_name="notification_template")
    op.drop_table("notification_template")
    op.drop_index("ix_notification_recipient_user_id", table_name="notification_recipient")
    op.drop_index("ix_notification_recipient_message_id", table_name="notification_recipient")
    op.drop_table("notification_recipient")
    op.drop_index("ix_notification_message_type", table_name="notification_message")
    op.drop_index("ix_notification_message_business_key", table_name="notification_message")
    op.drop_table("notification_message")
