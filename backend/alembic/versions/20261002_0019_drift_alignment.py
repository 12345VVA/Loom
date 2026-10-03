"""真库 drift 修正：索引对齐 + 类型对齐 AutoString + 删残留列 + nullable 收紧

针对真库（public）与 baseline DDL 的历史漂移，逐项实证后手写，全部幂等
（IF EXISTS / IF NOT EXISTS / 幂等 ALTER）——从 baseline 全新建库与历史
漂移真库两条路径均可直接执行：
- 索引：definition_version 表历史重建未删旧名（ix_workflow_def_version_*
  与新名 ix_workflow_definition_version_* 列完全相同），删旧名冗余对；
  补齐 baseline 有而真库缺的 ix_workflow_artifact_delete_time、
  ix_workflow_execution_log_diff_base_log_id（演练 schema 均有、真库缺）
- 类型：content/request_options/test_set_snapshot 真库为 TEXT，模型期望
  AutoString——PG 无限长 VARCHAR 与 TEXT 存储等价，ALTER 仅改列声明，
  零数据迁移（实测 content 最大 27000 字符）
- workflow_eval_test_set.definition_snapshot：模型已移除，真库残留
  （实测 0 行非空数据，drop 零丢失）
- workflow_execution_log.payload_type：模型非空（default="full"），
  真库可空（实测 0 行 NULL，收紧零失败）

Revision ID: 20261002_0019
Revises: 20261002_0002
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261002_0019"
down_revision = "20261002_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 索引命名对齐：删历史残留的旧名冗余索引（列与新名完全相同）
    op.execute("DROP INDEX IF EXISTS ix_workflow_def_version_definition_id_created_at")
    op.execute("DROP INDEX IF EXISTS ix_workflow_def_version_definition_id_status")

    # 2) 补齐真库缺失的两个索引（baseline DDL 均有定义）
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_artifact_delete_time ON workflow_artifact (delete_time)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_execution_log_diff_base_log_id "
        "ON workflow_execution_log (diff_base_log_id)"
    )

    # 2.1) 版本表复合索引：真库历史手工建、baseline 无——补进新建库路径
    # （真库 IF NOT EXISTS 跳过；模型侧已补元数据定义）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_definition_id_created_at "
        "ON workflow_definition_version (definition_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_definition_id_status "
        "ON workflow_definition_version (definition_id, status)"
    )

    # 3) 类型对齐：TEXT -> 无限长 VARCHAR（AutoString 的 PG 形态，存储等价）
    op.alter_column(
        "ai_model_call_log",
        "request_options",
        existing_type=sa.Text(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "workflow_artifact",
        "content",
        existing_type=sa.Text(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "workflow_eval_run",
        "test_set_snapshot",
        existing_type=sa.Text(),
        type_=sa.String(),
        existing_nullable=True,
    )

    # 4) 删模型已移除的残留列（0 行非空数据实证）
    op.execute("ALTER TABLE workflow_eval_test_set DROP COLUMN IF EXISTS definition_snapshot")

    # 5) payload_type 收紧非空（0 行 NULL 实证）
    op.alter_column(
        "workflow_execution_log",
        "payload_type",
        existing_type=sa.String(length=20),
        nullable=False,
    )


def downgrade() -> None:
    # 反向仅供参考：definition_snapshot 的历史数据不可恢复
    op.alter_column(
        "workflow_execution_log",
        "payload_type",
        existing_type=sa.String(length=20),
        nullable=True,
    )
    op.add_column(
        "workflow_eval_test_set",
        sa.Column("definition_snapshot", sa.VARCHAR(), nullable=False),
    )
    op.alter_column(
        "workflow_eval_run",
        "test_set_snapshot",
        existing_type=sa.String(),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "workflow_artifact",
        "content",
        existing_type=sa.String(),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "ai_model_call_log",
        "request_options",
        existing_type=sa.String(),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.execute("DROP INDEX IF EXISTS ix_workflow_execution_log_diff_base_log_id")
    op.execute("DROP INDEX IF EXISTS ix_workflow_artifact_delete_time")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_def_version_definition_id_status "
        "ON workflow_definition_version (definition_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_def_version_definition_id_created_at "
        "ON workflow_definition_version (definition_id, created_at)"
    )
