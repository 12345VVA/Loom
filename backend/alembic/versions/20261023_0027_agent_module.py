"""agent 模块九表（智能体定义/草稿/快照/发布记录/会话/消息/轨迹/工具日志/工具资源）

Revision ID: 20261023_0027
Revises: 20261022_0026
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261023_0027"
down_revision = "20261022_0026"
branch_labels = None
depends_on = None

# 建表走 PG DDL（0002/0022/0026 模式，IF NOT EXISTS 幂等可重放）：SQLite 开发路径由 init_db 的
# create_all 自动建表不经 alembic，迁移链正统路径是 PG 空库部署/CI。列类型与模型
# agent.model.agent 九表严格对齐（AutoString→VARCHAR，Text→TEXT，bool→BOOLEAN，float→DOUBLE PRECISION），
# 索引名与模型 Field(index=True)/__table_args__ 一致（test_migration_drift 按名字+列集合对账）。
# partial unique ×2：profile.code 软删后可重建；publish_record 每智能体至多一条 is_current
# （并发发布的库级兜底，uq_agent_publish_current；条件用 boolean truthy——PG boolean 不可与 integer 比较）。
# BaseEntity 三列（id/created_at/updated_at/delete_time）全表一致（项目惯例，含运行时表）。

_PROFILE_DDL = """
CREATE TABLE IF NOT EXISTS agent_profile (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    model_profile_code VARCHAR(100) NOT NULL,
    system_prompt TEXT,
    tools TEXT,
    temperature DOUBLE PRECISION NOT NULL,
    max_tokens INTEGER NOT NULL,
    max_tool_rounds INTEGER NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    enable_memory BOOLEAN NOT NULL,
    enabled BOOLEAN NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_by INTEGER,
    PRIMARY KEY (id)
)
"""

_DRAFT_DDL = """
CREATE TABLE IF NOT EXISTS agent_profile_draft (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    profile_id INTEGER NOT NULL UNIQUE,
    draft_version INTEGER NOT NULL,
    draft_json TEXT,
    draft_hash VARCHAR(64),
    synced_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
)
"""

_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS agent_profile_snapshot (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    profile_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    source_draft_version INTEGER NOT NULL,
    snapshot_hash VARCHAR(64) NOT NULL,
    agent_name VARCHAR(150) NOT NULL,
    agent_code VARCHAR(100) NOT NULL,
    snapshot_json TEXT,
    created_by INTEGER,
    PRIMARY KEY (id)
)
"""

_PUBLISH_RECORD_DDL = """
CREATE TABLE IF NOT EXISTS agent_profile_publish_record (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    profile_id INTEGER NOT NULL,
    snapshot_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    is_current BOOLEAN NOT NULL,
    rollback_from_snapshot_id INTEGER,
    operated_by INTEGER,
    published_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
)
"""

_SESSION_DDL = """
CREATE TABLE IF NOT EXISTS agent_session (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    session_code VARCHAR(100) NOT NULL,
    profile_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    title VARCHAR(200),
    run_mode VARCHAR(20) NOT NULL,
    last_message_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
)
"""

_MESSAGE_DDL = """
CREATE TABLE IF NOT EXISTS agent_message (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    session_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    name VARCHAR(150),
    tool_call_id VARCHAR(150),
    token_count INTEGER,
    metadata TEXT,
    PRIMARY KEY (id)
)
"""

_RUN_TRACE_DDL = """
CREATE TABLE IF NOT EXISTS agent_run_trace (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    profile_id INTEGER NOT NULL,
    run_mode VARCHAR(20) NOT NULL,
    snapshot_id INTEGER,
    agent_code VARCHAR(100) NOT NULL,
    agent_name VARCHAR(150) NOT NULL,
    session_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    model_calls INTEGER NOT NULL,
    tool_rounds INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    duration_ms INTEGER,
    status VARCHAR(20) NOT NULL,
    error TEXT,
    PRIMARY KEY (id)
)
"""

_TOOL_CALL_LOG_DDL = """
CREATE TABLE IF NOT EXISTS agent_tool_call_log (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    trace_id INTEGER NOT NULL,
    tool_name VARCHAR(150) NOT NULL,
    args_summary TEXT,
    result_summary TEXT,
    duration_ms INTEGER,
    success BOOLEAN,
    error TEXT,
    PRIMARY KEY (id)
)
"""

_TOOL_RESOURCE_DDL = """
CREATE TABLE IF NOT EXISTS agent_tool_resource (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    tool_name VARCHAR(150) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    source_type VARCHAR(20) NOT NULL,
    level VARCHAR(30) NOT NULL,
    status BOOLEAN NOT NULL,
    schema_summary TEXT,
    prompt_metadata_json TEXT,
    metadata_hash VARCHAR(64) NOT NULL,
    created_by INTEGER,
    updated_by INTEGER,
    PRIMARY KEY (id)
)
"""

# (表名, 索引列) —— 与模型 Field(index=True) 一一对应（ix_{table}_{col}）
_INDEXED_COLUMNS: dict[str, tuple[str, ...]] = {
    "agent_profile": ("code", "name", "enabled", "status", "created_by"),
    "agent_profile_draft": ("profile_id",),
    "agent_profile_snapshot": ("profile_id", "snapshot_hash"),
    "agent_profile_publish_record": ("profile_id", "snapshot_id"),
    "agent_session": ("session_code", "profile_id", "user_id", "run_mode"),
    "agent_message": ("session_id",),
    "agent_run_trace": ("profile_id", "run_mode", "snapshot_id", "session_id", "user_id", "status"),
    "agent_tool_call_log": ("trace_id",),
    "agent_tool_resource": ("tool_name", "status"),
}

# partial unique（模型 __table_args__ 同名同条件）
_PARTIAL_UNIQUES = (
    ("uq_agent_profile_code", "agent_profile", "code", "delete_time IS NULL"),
    ("uq_agent_publish_current", "agent_profile_publish_record", "profile_id", "is_current"),
    ("uq_agent_tool_resource_name", "agent_tool_resource", "tool_name", "delete_time IS NULL"),
)


def upgrade() -> None:
    for ddl in (
        _PROFILE_DDL,
        _DRAFT_DDL,
        _SNAPSHOT_DDL,
        _PUBLISH_RECORD_DDL,
        _SESSION_DDL,
        _MESSAGE_DDL,
        _RUN_TRACE_DDL,
        _TOOL_CALL_LOG_DDL,
        _TOOL_RESOURCE_DDL,
    ):
        op.execute(ddl)

    for table, columns in _INDEXED_COLUMNS.items():
        for col in columns:
            op.create_index(f"ix_{table}_{col}", table, [col])
    for name, table, col, where in _PARTIAL_UNIQUES:
        op.create_index(name, table, [col], unique=True, postgresql_where=sa.text(where))


def downgrade() -> None:
    for name, table, _col, _where in _PARTIAL_UNIQUES:
        op.drop_index(name, table_name=table)
    for table, columns in _INDEXED_COLUMNS.items():
        for col in columns:
            op.drop_index(f"ix_{table}_{col}", table_name=table)
    for table in (
        "agent_tool_resource",
        "agent_tool_call_log",
        "agent_run_trace",
        "agent_message",
        "agent_session",
        "agent_profile_publish_record",
        "agent_profile_snapshot",
        "agent_profile_draft",
        "agent_profile",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
