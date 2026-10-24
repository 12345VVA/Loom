"""E15 渠道窗口动态化：存量模型窗口数据兜底（无 DDL，ai_model.context_window 列已存在）

Revision ID: 20261024_0028
Revises: 20261023_0027
Create Date: 2026-10-24
"""

from __future__ import annotations

from alembic import op

revision = "20261024_0028"
down_revision = "20261023_0027"
branch_labels = None
depends_on = None

# 设计二批 3.2（E15）规则 3：「常数 32000 仅存量迁移兜底，非未知模型推导下界」。
# 一期窗口校验按常数 32000 下限运行（所有绑定隐式假设 ≥32k）；E15 改为解析链动态最小窗口、
# 未知不放行。本迁移把**存量** chat 模型的未知窗口补为 32000（一期已验证假设的显式化），
# 使存量绑定在动态校验下不断；此后新建模型不填窗口 = 未知 = 发布/run 拒绝，由管理员录入
# 经验证的覆盖值。仅数据 UPDATE、无 schema 变更（test_migration_drift 不受影响）；
# SQLite 开发路径不经 alembic（init_db create_all），测试库数据由用例自建不受影响。

_UPGRADE_SQL = """
UPDATE ai_model
SET context_window = 32000
WHERE context_window IS NULL
  AND delete_time IS NULL
  AND model_type = 'chat'
  AND is_active
"""

_DOWNGRADE_SQL = """
UPDATE ai_model
SET context_window = NULL
WHERE context_window = 32000
  AND delete_time IS NULL
  AND model_type = 'chat'
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    # down 无法区分「本来就是 32000」与「本迁移填入的 32000」，统一置回 NULL（宽松语义）
    op.execute(_DOWNGRADE_SQL)
