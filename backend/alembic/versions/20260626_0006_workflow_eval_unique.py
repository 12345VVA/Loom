"""workflow_eval unique constraint

为 workflow_eval_case_result 增加 (eval_run_id, case_key) 联合唯一约束，
防止同一评估运行出现重复 case_key 导致回归对比 dict 映射覆盖、对比失真
（评审报告问题 4/5）。

说明：
- 联合普通索引 (eval_run_id, case_key) 已由 _ensure_indexes 自动补建，此处仅补唯一约束。
- init_db 的补列/补索引机制不支持约束，已有库须经此迁移补建；dev 新库由 create_all
  依据模型 __table_args__ 直接生成约束。
- 未加外键：全项目无 foreign_key 先例，且与软删除 delete_time 模式存在级联冲突风险。

Revision ID: 20260626_0006
Revises: 20260622_0005
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260626_0006"
down_revision = "20260622_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 生产部署前若已存在重复 (eval_run_id, case_key) 数据，需先清理再升级，否则约束创建失败
    with op.batch_alter_table("workflow_eval_case_result") as batch:
        batch.create_unique_constraint(
            "uq_workflow_eval_case_result_run_case_key",
            ["eval_run_id", "case_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_eval_case_result") as batch:
        batch.drop_constraint(
            "uq_workflow_eval_case_result_run_case_key",
            type_="unique",
        )
