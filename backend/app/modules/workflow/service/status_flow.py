"""工作流实例状态机（三期B7 / WF-P2-16）：合法迁移的单一权威定义。

此前 4+ 处 CAS 位点各自内联硬编码 from/to 状态，新增位点容易写出
非法迁移（如 success → running）而无任何拦截。本模块收敛为常量表 +
表驱动 CAS helper；新增状态迁移位点一律经 cas_transition，非法迁移
在开发期即抛错。

两段式启动（一期 D2）：pending（已入队待执行）→ running（执行体开跑）。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import update

from app.modules.workflow.model.workflow import WorkflowInstance

# 合法状态迁移表：key = 当前状态，value = 允许迁入的状态集合。
# running → running：current_node 推进（_set_current_node_sync）等「保持运行」的
# 条件更新也走该通道。
# failed → running：failed 实例断点续跑（三期B7 / WF-P2-17）——仅当存在可恢复
# checkpoint 时由 resume_instance 放行（表只管状态机合法性，业务前置在调用方）。
ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset({"running", "paused", "success", "failed", "cancelled"}),
    "paused": frozenset({"running", "failed", "cancelled"}),
    "success": frozenset(),
    "failed": frozenset({"running"}),
    "cancelled": frozenset(),
}

ALL_STATUSES = frozenset(ALLOWED_STATUS_TRANSITIONS)
# 业务终态：failed 虽有 running 出边（断点续跑）仍属业务终态——cancel 前置检查等
# 场景用它；与迁移表「零出边」不是同一概念，故显式定义而非派生。
TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """判定 from → to 是否为合法迁移（未登记状态一律非法）。"""
    return to_status in ALLOWED_STATUS_TRANSITIONS.get(from_status, frozenset())


def cas_transition(
    session: Any,
    instance_id: int,
    from_statuses: Iterable[str],
    to_status: str,
    extra_values: dict[str, Any] | None = None,
) -> int:
    """表驱动的状态迁移 CAS：仅当当前状态 ∈ from_statuses 且迁移合法时置为 to_status。

    非法迁移（表未登记）抛 ValueError——调用方写错状态机时在开发期暴露，
    而非静默落库。返回受影响行数（0 = 状态已被并发改走，由调用方复查/拒绝）。
    """
    sources = list(from_statuses)
    for s in sources:
        if not is_valid_transition(s, to_status):
            raise ValueError(f"非法状态迁移: {s} → {to_status}（见 status_flow.ALLOWED_STATUS_TRANSITIONS）")
    stmt = (
        update(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id, WorkflowInstance.status.in_(sources))
        .values(status=to_status, **(extra_values or {}))
    )
    return session.execute(stmt).rowcount
