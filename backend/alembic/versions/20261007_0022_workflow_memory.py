"""workflow_memory 长期记忆表 + workflow_definition.memory_write_enabled 写入开关

Revision ID: 20261007_0022
Revises: 20261007_0021
Create Date: 2026-10-07
"""

from __future__ import annotations

from alembic import op

revision = "20261007_0022"
down_revision = "20261007_0021"
branch_labels = None
depends_on = None

# 建表走 PG DDL（0002 模式，IF NOT EXISTS 幂等可重放）：SQLite 开发路径由 init_db 的
# create_all 自动建表不经 alembic，迁移链正统路径是 PG 空库部署/CI。列类型与模型
# workflow_memory.WorkflowMemory 严格对齐（AutoString→VARCHAR，Text→TEXT），
# 索引名与模型 __table_args__ 一致（test_migration_drift 按名字+列集合对账）。
_UPGRADE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS workflow_memory (
        id SERIAL NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        delete_time TIMESTAMP WITH TIME ZONE,
        definition_id INTEGER NOT NULL,
        memory_env VARCHAR(20) NOT NULL,
        memory_type VARCHAR(20) NOT NULL,
        memory_key VARCHAR(200),
        content VARCHAR(4000) NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        tags VARCHAR(2000) NOT NULL,
        embedding TEXT,
        embedding_space VARCHAR(150),
        source_instance_id INTEGER,
        source_node_id VARCHAR(100),
        source_run_type VARCHAR(20),
        created_by_user_id INTEGER,
        updated_by_user_id INTEGER,
        last_accessed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_memory_definition_id ON workflow_memory (definition_id)",
    "CREATE INDEX IF NOT EXISTS ix_workflow_memory_memory_key ON workflow_memory (memory_key)",
    # Field(index=True) 字段：create_all 对新表自动建单列索引，此处对齐
    # （delete_time 来自 BaseEntity 自带 index=True；source_instance_id 为模型显式声明）
    "CREATE INDEX IF NOT EXISTS ix_workflow_memory_delete_time ON workflow_memory (delete_time)",
    "CREATE INDEX IF NOT EXISTS ix_workflow_memory_source_instance_id ON workflow_memory (source_instance_id)",
    "CREATE INDEX IF NOT EXISTS ix_workflow_memory_definition_env ON workflow_memory (definition_id, memory_env, delete_time)",
    # partial unique index：软删行不参与判定（模型侧 sqlite_where/postgresql_where 同条件）
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_key ON workflow_memory (definition_id, memory_env, memory_key) "
    "WHERE memory_key IS NOT NULL AND delete_time IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_hash ON workflow_memory (definition_id, memory_env, content_hash) "
    "WHERE memory_key IS NULL AND delete_time IS NULL",
)


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(stmt)

    # workflow_definition 加记忆写入开关。NOT NULL 列三步加（ADD 可空 → 回填 → SET NOT NULL）：
    # 最终结构与 create_all 完全一致（无 server default），PG 11+ 均为元数据级操作
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite 加 NOT NULL 列必须带 DEFAULT；开发路径不走 alembic，此分支仅为手动验证保留
        _sqlite_add_column_if_missing(bind, "workflow_definition", "memory_write_enabled", "BOOLEAN DEFAULT 1 NOT NULL")
    else:
        op.execute("ALTER TABLE workflow_definition ADD COLUMN IF NOT EXISTS memory_write_enabled BOOLEAN")
        op.execute("UPDATE workflow_definition SET memory_write_enabled = TRUE WHERE memory_write_enabled IS NULL")
        op.execute("ALTER TABLE workflow_definition ALTER COLUMN memory_write_enabled SET NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return  # SQLite 不支持 DROP COLUMN；开发路径不走 alembic
    # DROP TABLE 自动带走其全部索引
    op.execute("ALTER TABLE workflow_definition DROP COLUMN IF EXISTS memory_write_enabled")
    op.execute("DROP TABLE IF EXISTS workflow_memory")


def _sqlite_add_column_if_missing(bind, table: str, column: str, ddl: str) -> None:
    """SQLite 无 IF NOT EXISTS：查 PRAGMA table_info 已有列则跳过（0021 同款）。"""
    cols = [row[1] for row in bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        bind.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
