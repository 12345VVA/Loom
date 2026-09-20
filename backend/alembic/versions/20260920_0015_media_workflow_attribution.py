"""media_asset 工作流来源归属字段

生图节点转存（source_type=workflow）此前不写 created_by 与实例/定义/节点归属，
导致：普通用户在资源库看不到自己工作流产出的资产（列表按 created_by 过滤）、
打开资产文件 403（/uploads 归属校验按 created_by）、实例与资产双向不可追溯。

三列均 nullable：非工作流来源（ai_task/ai_sync/upload）为空。created_by 归属
由 workflow_instance_id_ctx 上下文关联实例后取 instance.user_id 写入。
历史 workflow 资产归属为空，不做回填。

Revision ID: 20260920_0015
Revises: 20260920_0014
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_0015"
down_revision = "20260920_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_asset") as batch:
        batch.add_column(sa.Column("workflow_instance_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("workflow_definition_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("workflow_node_id", sa.String(length=100), nullable=True))
        batch.create_index("ix_media_asset_workflow_instance_id", ["workflow_instance_id"])


def downgrade() -> None:
    with op.batch_alter_table("media_asset") as batch:
        batch.drop_index("ix_media_asset_workflow_instance_id")
        batch.drop_column("workflow_node_id")
        batch.drop_column("workflow_definition_id")
        batch.drop_column("workflow_instance_id")
