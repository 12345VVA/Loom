"""workflow_artifact 产物实体表

执行成功终态时把 end 节点渲染的 workflow_output 自适应分类落地为产物实体
（image 引用 media_asset / text / json），与执行快照（state_data/执行日志）
解耦：监控看过程，产物看结果。

instance_id/definition_id/user_id 建索引：按实例拉取产物、按定义汇总、
user_id 触发 BaseAdminCrudService 自动数据权限。content 为 TEXT，超阈值
载荷经 offload_payload 分离到对象存储（content_ref）。

Revision ID: 20260920_0016
Revises: 20260920_0015
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_0016"
down_revision = "20260920_0015"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    inspector = sa.inspect(op.get_bind())
    return "workflow_artifact" in inspector.get_table_names()


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        "workflow_artifact",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("delete_time", sa.DateTime(), nullable=True),
        sa.Column("instance_id", sa.Integer(), nullable=False, index=True),
        sa.Column("definition_id", sa.Integer(), nullable=False, index=True),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("field_key", sa.String(length=150), nullable=False),
        sa.Column("field_path", sa.String(length=200), nullable=True),
        sa.Column("asset_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("media_asset_id", sa.Integer(), nullable=True, index=True),
        sa.Column("storage_url", sa.String(length=1000), nullable=True),
        sa.Column("original_url", sa.String(length=1000), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_ref", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workflow_artifact")
