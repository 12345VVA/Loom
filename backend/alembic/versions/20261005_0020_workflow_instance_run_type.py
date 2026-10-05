"""workflow_instance/workflow_artifact 加 run_type：区分正式/试运行/评估实例

三类活动（正式执行/编辑器试运行/批量评估）此前混写同一实例表无法区分，导致
列表混淆、测试实例产物污染生产产物库、测试失败误发正式通知。本次为实例表加
run_type（production|trial|eval）+ eval_run_id 回溯评估批次；产物表冗余 run_type
供测试产物打标区分/清理。均幂等（IF NOT EXISTS），存量行默认 production。

Revision ID: 20261005_0020
Revises: 20261002_0019
Create Date: 2026-10-05
"""

from __future__ import annotations

from alembic import op

revision = "20261005_0020"
down_revision = "20261002_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持 ADD COLUMN IF NOT EXISTS，用带列存在性判断的方言分支（对齐 0019 幂等风格）
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_add_column_if_missing("workflow_instance", "run_type", "VARCHAR(20) NOT NULL DEFAULT 'production'")
        _sqlite_add_column_if_missing("workflow_instance", "eval_run_id", "INTEGER")
        _sqlite_add_column_if_missing("workflow_artifact", "run_type", "VARCHAR(20) NOT NULL DEFAULT 'production'")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_instance_run_type ON workflow_instance (run_type)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_instance_eval_run_id ON workflow_instance (eval_run_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_artifact_run_type ON workflow_artifact (run_type)")
    else:
        op.execute("ALTER TABLE workflow_instance ADD COLUMN IF NOT EXISTS run_type VARCHAR(20) NOT NULL DEFAULT 'production'")
        op.execute("ALTER TABLE workflow_instance ADD COLUMN IF NOT EXISTS eval_run_id INTEGER")
        op.execute("ALTER TABLE workflow_artifact ADD COLUMN IF NOT EXISTS run_type VARCHAR(20) NOT NULL DEFAULT 'production'")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_instance_run_type ON workflow_instance (run_type)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_instance_eval_run_id ON workflow_instance (eval_run_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_artifact_run_type ON workflow_artifact (run_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_artifact_run_type")
    op.execute("DROP INDEX IF EXISTS ix_workflow_instance_eval_run_id")
    op.execute("DROP INDEX IF EXISTS ix_workflow_instance_run_type")
    op.execute("ALTER TABLE workflow_artifact DROP COLUMN IF EXISTS run_type")
    op.execute("ALTER TABLE workflow_instance DROP COLUMN IF EXISTS eval_run_id")
    op.execute("ALTER TABLE workflow_instance DROP COLUMN IF EXISTS run_type")


def _sqlite_add_column_if_missing(table: str, column: str, ddl: str) -> None:
    """SQLite 无 IF NOT EXISTS：查 PRAGMA table_info 已有列则跳过。"""
    bind = op.get_bind()
    cols = [row[1] for row in bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        bind.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
