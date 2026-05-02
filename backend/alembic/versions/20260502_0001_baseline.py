"""baseline

Revision ID: 20260502_0001
Revises:
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "20260502_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Baseline revision for existing Loom schema."""
    pass


def downgrade() -> None:
    """Baseline revision has no downgrade operations."""
    pass
