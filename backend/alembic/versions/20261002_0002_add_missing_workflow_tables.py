"""add missing workflow tables (workflow_annotation, workflow_definition_version)

修复 baseline 迁移漏掉的 2 张业务表：
- workflow_annotation: 工作流评估人工标注模型
- workflow_definition_version: 工作流版本管理与快照模型

Revision ID: 20261002_0002
Revises: 20261002_0018
Create Date: 2026-10-02
"""

from __future__ import annotations

from alembic import op

revision = "20261002_0002"
down_revision = "20261002_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 workflow_annotation 表及索引
    op.execute(
        """CREATE TABLE IF NOT EXISTS workflow_annotation (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	case_result_id INTEGER NOT NULL, 
	annotator_user_id INTEGER, 
	label VARCHAR(20) NOT NULL, 
	score FLOAT, 
	reason VARCHAR(500), 
	is_gold BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_annotation_case_result_id ON workflow_annotation (case_result_id)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_annotation_annotator_user_id ON workflow_annotation (annotator_user_id)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_annotation_is_gold ON workflow_annotation (is_gold)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_annotation_delete_time ON workflow_annotation (delete_time)
"""
    )

    # 2. 创建 workflow_definition_version 表及索引
    op.execute(
        """CREATE TABLE IF NOT EXISTS workflow_definition_version (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	definition_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	graph_json VARCHAR(100000) NOT NULL, 
	change_note VARCHAR(500), 
	parent_version_id INTEGER, 
	published_at TIMESTAMP WITH TIME ZONE, 
	published_by INTEGER, 
	user_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_def_version_def_no UNIQUE (definition_id, version_no)
)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_definition_id ON workflow_definition_version (definition_id)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_parent_version_id ON workflow_definition_version (parent_version_id)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_published_by ON workflow_definition_version (published_by)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_user_id ON workflow_definition_version (user_id)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_status ON workflow_definition_version (status)
"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_workflow_definition_version_delete_time ON workflow_definition_version (delete_time)
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_annotation CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_definition_version CASCADE")
