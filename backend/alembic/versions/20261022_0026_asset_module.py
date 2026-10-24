"""asset 模块三表（角色/场景/风格）+ media_asset 产物回链增列

Revision ID: 20261022_0026
Revises: 20261019_0025
Create Date: 2026-10-22
"""

from __future__ import annotations

from alembic import op

revision = "20261022_0026"
down_revision = "20261019_0025"
branch_labels = None
depends_on = None

# 建表走 PG DDL（0002/0022 模式，IF NOT EXISTS 幂等可重放）：SQLite 开发路径由 init_db 的
# create_all 自动建表不经 alembic，迁移链正统路径是 PG 空库部署/CI。列类型与模型
# asset.model.asset 三表严格对齐（AutoString→VARCHAR，Text→TEXT），
# 索引名与模型 Field(index=True)/__table_args__ 一致（test_migration_drift 按名字+列集合对账）。
# partial unique：软删行不参与 code 唯一判定（模型侧 sqlite_where/postgresql_where 同条件）。

_CHARACTER_DDL = """
CREATE TABLE IF NOT EXISTS asset_character (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    status VARCHAR(50) NOT NULL,
    category VARCHAR(100),
    appearance_prompt TEXT,
    negative_prompt TEXT,
    attributes TEXT,
    voice_prompt TEXT,
    ref_image_ids TEXT,
    preferred_profile_code VARCHAR(100),
    preferred_size VARCHAR(50),
    tags TEXT,
    cover_media_id INTEGER,
    incompatible_tags TEXT,
    created_by INTEGER,
    PRIMARY KEY (id)
)
"""

_SCENE_DDL = """
CREATE TABLE IF NOT EXISTS asset_scene (
    id SERIAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delete_time TIMESTAMP WITH TIME ZONE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    status VARCHAR(50) NOT NULL,
    category VARCHAR(100),
    appearance_prompt TEXT,
    negative_prompt TEXT,
    ref_image_ids TEXT,
    preferred_profile_code VARCHAR(100),
    preferred_size VARCHAR(50),
    tags TEXT,
    cover_media_id INTEGER,
    created_by INTEGER,
    PRIMARY KEY (id)
)
"""

# 风格表与场景表同构（DDL 相同，表名不同）
_STYLE_DDL = _SCENE_DDL.replace("asset_scene", "asset_style")

# media_asset 产物回链增列（asset 模块，决策 #23/#29）：派生冗余列规避 SQLite/PG JSON 方言分裂；
# tags 为扩展级预埋（核心期任何 DTO/接口不读写）
_MEDIA_COLUMNS = (
    ("asset_refs", "TEXT", False),
    ("source_character_id", "INTEGER", True),
    ("source_scene_id", "INTEGER", True),
    ("source_style_id", "INTEGER", True),
    ("composed_prompt_hash", "VARCHAR(64)", True),
    ("composer_version", "VARCHAR(16)", False),
    ("tags", "TEXT", False),
)


def upgrade() -> None:
    # --- 新表（PG；SQLite 由 create_all 覆盖）---
    op.execute(_CHARACTER_DDL)
    op.execute(_SCENE_DDL)
    op.execute(_STYLE_DDL)

    # 索引/增列一律 IF NOT EXISTS 幂等（SQLite 3.3+/PG 9.5+ 双支持）：真实升级路径上库可能
    # 先被 init_db 的 create_all 预建过结构（启动先于迁移），op.create_index/add_column 无
    # 存在性守卫会 DuplicateTable 中断整链。索引名/列集合不变，test_migration_drift 对账不受影响。
    for table in ("asset_character", "asset_scene", "asset_style"):
        for col in ("code", "name", "status", "category", "cover_media_id", "created_by", "delete_time"):
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})")
    # partial unique（软删行不参与判定；模型 __table_args__ 同名同条件）
    for table in ("asset_character", "asset_scene", "asset_style"):
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_{table.split('_')[-1]}_code"
            f" ON {table} (code) WHERE delete_time IS NULL"
        )

    # --- media_asset 回链增列（ADD COLUMN IF NOT EXISTS 为 PG 9.6+ 语法；SQLite 开发路径
    #     不经 alembic，见文件头注）---
    for col_name, col_ddl, indexed in _MEDIA_COLUMNS:
        op.execute(f"ALTER TABLE media_asset ADD COLUMN IF NOT EXISTS {col_name} {col_ddl}")
        if indexed:
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_media_asset_{col_name} ON media_asset ({col_name})")


def downgrade() -> None:
    for col_name, _col_type, indexed in reversed(_MEDIA_COLUMNS):
        if indexed:
            op.drop_index(f"ix_media_asset_{col_name}", table_name="media_asset")
        op.drop_column("media_asset", col_name)

    for table in ("asset_style", "asset_scene", "asset_character"):
        op.drop_index(f"uq_asset_{table.split('_')[-1]}_code", table_name=table)
        for col in ("code", "name", "status", "category", "cover_media_id", "created_by", "delete_time"):
            op.drop_index(f"ix_{table}_{col}", table_name=table)
        op.execute(f"DROP TABLE IF EXISTS {table}")
