"""三期 B7（WF-P2-16）：合法状态迁移表集中与表驱动 CAS。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_status_flow.py -q
"""

from __future__ import annotations

import unittest

from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.status_flow import (
    ALLOWED_STATUS_TRANSITIONS,
    TERMINAL_STATUSES,
    cas_transition,
    is_valid_transition,
)


class TransitionTableTestCase(unittest.TestCase):
    def test_table_shape(self):
        """所有登记状态的迁移目标都自身登记在表中（无悬空状态）。"""
        for src, targets in ALLOWED_STATUS_TRANSITIONS.items():
            for tgt in targets:
                self.assertIn(tgt, ALLOWED_STATUS_TRANSITIONS, f"{src} → {tgt}：目标状态未登记")

    def test_terminal_states_shape(self):
        """success/cancelled 零出边；failed 仅可断点续跑（WF-P2-17）。"""
        self.assertEqual(TERMINAL_STATUSES, {"success", "failed", "cancelled"})
        self.assertEqual(ALLOWED_STATUS_TRANSITIONS["success"], frozenset())
        self.assertEqual(ALLOWED_STATUS_TRANSITIONS["cancelled"], frozenset())
        self.assertEqual(ALLOWED_STATUS_TRANSITIONS["failed"], frozenset({"running"}))

    def test_business_transitions(self):
        """关键业务迁移锁定（两段式启动 / resume / cancel / 终态收尾 / failed 续跑）。"""
        self.assertTrue(is_valid_transition("pending", "running"))
        self.assertTrue(is_valid_transition("running", "success"))
        self.assertTrue(is_valid_transition("running", "failed"))
        self.assertTrue(is_valid_transition("running", "paused"))
        self.assertTrue(is_valid_transition("paused", "running"))
        self.assertTrue(is_valid_transition("failed", "running"))  # WF-P2-17 断点续跑
        for s in ("pending", "running", "paused"):
            self.assertTrue(is_valid_transition(s, "cancelled"), s)
        self.assertTrue(is_valid_transition("running", "running"))  # current_node 推进

    def test_invalid_transitions(self):
        """终态不可随意迁出；跨终态迁移非法。"""
        for src in ("success", "cancelled"):
            for tgt in ("running", "paused", "pending", "success", "failed", "cancelled"):
                self.assertFalse(is_valid_transition(src, tgt), f"{src} → {tgt}")
        # failed 仅允许 → running（断点续跑），其余迁出非法
        for tgt in ("paused", "pending", "success", "failed", "cancelled"):
            self.assertFalse(is_valid_transition("failed", tgt), f"failed → {tgt}")
        self.assertFalse(is_valid_transition("success", "running"))
        self.assertFalse(is_valid_transition("unknown_status", "running"))


class CasTransitionTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            definition = WorkflowDefinition(name="t", code="t-flow", owner_id=1)
            session.add(definition)
            session.commit()
            instance = WorkflowInstance(
                definition_id=definition.id, thread_id=f"test-{definition.id}", status="pending", state_data="{}"
            )
            session.add(instance)
            session.commit()
            self.instance_id = instance.id
            self.definition_id = definition.id

    def test_legal_transition_applies(self):
        with Session(self.engine) as session:
            rowcount = cas_transition(session, self.instance_id, ("pending",), "running")
            session.commit()
        self.assertEqual(rowcount, 1)
        with Session(self.engine) as session:
            self.assertEqual(session.get(WorkflowInstance, self.instance_id).status, "running")

    def test_illegal_transition_raises(self):
        """非法迁移（表未登记）在开发期抛 ValueError，而非静默落库。"""
        with Session(self.engine) as session:
            with self.assertRaises(ValueError) as cm:
                cas_transition(session, self.instance_id, ("pending",), "success")
            session.rollback()
        self.assertIn("非法状态迁移", str(cm.exception))
        # 状态未被改动
        with Session(self.engine) as session:
            self.assertEqual(session.get(WorkflowInstance, self.instance_id).status, "pending")

    def test_status_mismatch_returns_zero(self):
        """当前状态不在 from_statuses：rowcount=0（并发改走，由调用方复查/拒绝）。"""
        with Session(self.engine) as session:
            rowcount = cas_transition(session, self.instance_id, ("running",), "success")
        self.assertEqual(rowcount, 0)

    def test_extra_values_applied(self):
        with Session(self.engine) as session:
            cas_transition(
                session,
                self.instance_id,
                ("pending",),
                "failed",
                extra_values={"error_message": "boom"},
            )
            session.commit()
        with Session(self.engine) as session:
            inst = session.get(WorkflowInstance, self.instance_id)
            self.assertEqual(inst.status, "failed")
            self.assertEqual(inst.error_message, "boom")


if __name__ == "__main__":
    unittest.main()
