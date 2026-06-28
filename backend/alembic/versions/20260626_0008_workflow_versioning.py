"""workflow_definition_version 版本管理 + 发布管理

引入工作流定义的版本与发布管理（纯版本表模型）：
- 新建 workflow_definition_version 表，graph_json 从主表搬到本表（草稿/发布均存版本表）
- 主表 workflow_definition 加 current_version_id / draft_version_id 指针，删除 graph_json
- workflow_instance 加 version_id（本次执行所用版本，存量 NULL）
- workflow_eval_run 加 definition_version_id（精确版本关联，替代 graph_json_snapshot；snapshot 列保留作 fallback）

存量迁移：每个 definition 的 graph_json → 建一条 published(version_no=1) + 一条 draft(version_no=2)，
回填主表指针。存量 instance.version_id / eval_run.definition_version_id 留 NULL。

downgrade 不还原主表 graph_json 数据（语义不可逆），仅反向结构。迁移前请备份。
dev 新库由 create_all 建版本表；旧 dev/sqlite 库由 _ensure_sqlite_compatible_schema 补指针列。

Revision ID: 20260626_0008
Revises: 20260626_0007
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

revision = "20260626_0008"
down_revision = "20260626_0007"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa_inspect(bind).get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return table in set(sa_inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 建版本表（create_all 可能已建，幂等判断）
    if not _has_table(bind, "workflow_definition_version"):
        op.create_table(
            "workflow_definition_version",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("definition_id", sa.Integer(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("graph_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("change_note", sa.String(length=500), nullable=True),
            sa.Column("parent_version_id", sa.Integer(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("published_by", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("delete_time", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "definition_id", "version_no", name="uq_workflow_def_version_def_no"
            ),
        )
        op.create_index("ix_workflow_definition_version_definition_id", "workflow_definition_version", ["definition_id"])
        op.create_index("ix_workflow_definition_version_status", "workflow_definition_version", ["status"])
        op.create_index("ix_workflow_definition_version_parent_version_id", "workflow_definition_version", ["parent_version_id"])
        op.create_index("ix_workflow_definition_version_published_by", "workflow_definition_version", ["published_by"])
        op.create_index("ix_workflow_definition_version_user_id", "workflow_definition_version", ["user_id"])
        op.create_index(
            "ix_workflow_definition_version_definition_id_created_at",
            "workflow_definition_version",
            ["definition_id", "created_at"],
        )
        op.create_index(
            "ix_workflow_definition_version_definition_id_status",
            "workflow_definition_version",
            ["definition_id", "status"],
        )

    # 2. 主表加指针列
    with op.batch_alter_table("workflow_definition") as batch:
        if not _has_column(bind, "workflow_definition", "current_version_id"):
            batch.add_column(sa.Column("current_version_id", sa.Integer(), nullable=True))
        if not _has_column(bind, "workflow_definition", "draft_version_id"):
            batch.add_column(sa.Column("draft_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_workflow_definition_current_version_id", "workflow_definition", ["current_version_id"])
    op.create_index("ix_workflow_definition_draft_version_id", "workflow_definition", ["draft_version_id"])

    # 3. instance 加 version_id
    if not _has_column(bind, "workflow_instance", "version_id"):
        with op.batch_alter_table("workflow_instance") as batch:
            batch.add_column(sa.Column("version_id", sa.Integer(), nullable=True))
    op.create_index("ix_workflow_instance_version_id", "workflow_instance", ["version_id"])

    # 4. eval_run 加 definition_version_id（不动 graph_json_snapshot 列）
    if not _has_column(bind, "workflow_eval_run", "definition_version_id"):
        with op.batch_alter_table("workflow_eval_run") as batch:
            batch.add_column(sa.Column("definition_version_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_workflow_eval_run_definition_version_id", "workflow_eval_run", ["definition_version_id"]
    )

    # 5. 存量数据迁移：仅当主表仍存在 graph_json 列（旧库）；新库无此列则跳过
    if _has_column(bind, "workflow_definition", "graph_json"):
        now = datetime.utcnow()
        defs = bind.execute(
            text("SELECT id, graph_json FROM workflow_definition WHERE delete_time IS NULL")
        ).fetchall()
        for d_id, gj in defs:
            # 幂等：已迁移过的 definition 跳过
            already = bind.execute(
                text("SELECT 1 FROM workflow_definition_version WHERE definition_id = :did LIMIT 1"),
                {"did": d_id},
            ).fetchone()
            if already:
                continue

            graph = gj or "{}"
            # published v1
            bind.execute(
                text(
                    "INSERT INTO workflow_definition_version "
                    "(definition_id, version_no, status, graph_json, change_note, parent_version_id, "
                    " published_at, published_by, user_id, created_at, updated_at) "
                    "VALUES (:did, 1, 'published', :gj, :note, NULL, :now, NULL, :uid, :now, :now)"
                ),
                {"did": d_id, "gj": graph, "note": "初始迁移快照", "now": now, "uid": None},
            )
            pub_id = bind.execute(
                text(
                    "SELECT id FROM workflow_definition_version "
                    "WHERE definition_id = :did AND version_no = 1"
                ),
                {"did": d_id},
            ).scalar()
            # draft v2（graph 复制自 published，parent 指向它）
            bind.execute(
                text(
                    "INSERT INTO workflow_definition_version "
                    "(definition_id, version_no, status, graph_json, change_note, parent_version_id, "
                    " published_at, published_by, user_id, created_at, updated_at) "
                    "VALUES (:did, 2, 'draft', :gj, NULL, :pub, NULL, NULL, :uid, :now, :now)"
                ),
                {"did": d_id, "gj": graph, "pub": pub_id, "now": now, "uid": None},
            )
            draft_id = bind.execute(
                text(
                    "SELECT id FROM workflow_definition_version "
                    "WHERE definition_id = :did AND version_no = 2"
                ),
                {"did": d_id},
            ).scalar()
            bind.execute(
                text(
                    "UPDATE workflow_definition SET current_version_id = :pub, draft_version_id = :draft "
                    "WHERE id = :did"
                ),
                {"pub": pub_id, "draft": draft_id, "did": d_id},
            )

        # 迁移完成后删除主表 graph_json 列
        with op.batch_alter_table("workflow_definition") as batch:
            batch.drop_column("graph_json")


def downgrade() -> None:
    bind = op.get_bind()

    # 不还原主表 graph_json 数据（语义不可逆）；仅重建空列以恢复结构兼容旧模型读取
    if not _has_column(bind, "workflow_definition", "graph_json"):
        with op.batch_alter_table("workflow_definition") as batch:
            batch.add_column(sa.Column("graph_json", sa.Text(), nullable=True))

    op.drop_index("ix_workflow_eval_run_definition_version_id", table_name="workflow_eval_run")
    if _has_column(bind, "workflow_eval_run", "definition_version_id"):
        with op.batch_alter_table("workflow_eval_run") as batch:
            batch.drop_column("definition_version_id")

    op.drop_index("ix_workflow_instance_version_id", table_name="workflow_instance")
    if _has_column(bind, "workflow_instance", "version_id"):
        with op.batch_alter_table("workflow_instance") as batch:
            batch.drop_column("version_id")

    op.drop_index("ix_workflow_definition_current_version_id", table_name="workflow_definition")
    op.drop_index("ix_workflow_definition_draft_version_id", table_name="workflow_definition")
    with op.batch_alter_table("workflow_definition") as batch:
        if _has_column(bind, "workflow_definition", "current_version_id"):
            batch.drop_column("current_version_id")
        if _has_column(bind, "workflow_definition", "draft_version_id"):
            batch.drop_column("draft_version_id")

    for ix in (
        "ix_workflow_definition_version_definition_id_created_at",
        "ix_workflow_definition_version_definition_id_status",
        "ix_workflow_definition_version_published_by",
        "ix_workflow_definition_version_user_id",
        "ix_workflow_definition_version_parent_version_id",
        "ix_workflow_definition_version_status",
        "ix_workflow_definition_version_definition_id",
    ):
        try:
            op.drop_index(ix, table_name="workflow_definition_version")
        except Exception:
            pass
    if _has_table(bind, "workflow_definition_version"):
        op.drop_table("workflow_definition_version")
