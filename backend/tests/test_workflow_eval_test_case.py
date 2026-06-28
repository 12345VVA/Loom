"""WorkflowTestCaseService 测试：items_count 同步、case_key 唯一、JSON 校验。"""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow_eval.model.test_set import WorkflowTestSet, WorkflowTestCaseUpdateRequest
from app.modules.workflow_eval.service.test_case_service import WorkflowTestCaseService


class TestCaseServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add(WorkflowTestSet(name="ts1", items_count=0))
            s.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_add_increments_items_count(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            svc.add({"test_set_id": 1, "case_key": "c1", "input_data": "{}"})
            svc.add({"test_set_id": 1, "case_key": "c2"})
        with Session(self.engine) as s:
            self.assertEqual(s.get(WorkflowTestSet, 1).items_count, 2)

    def test_add_duplicate_case_key_rejected(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            svc.add({"test_set_id": 1, "case_key": "c1"})
            with self.assertRaises(HTTPException) as cm:
                svc.add({"test_set_id": 1, "case_key": "c1"})
            self.assertEqual(cm.exception.status_code, 400)

    def test_add_invalid_json_rejected(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            with self.assertRaises(HTTPException):
                svc.add({"test_set_id": 1, "case_key": "c1", "input_data": "{not json"})

    def test_add_unknown_test_set_rejected(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            with self.assertRaises(HTTPException):
                svc.add({"test_set_id": 999, "case_key": "c1"})

    def test_delete_decrements_items_count(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            c1 = svc.add({"test_set_id": 1, "case_key": "c1"})
            svc.add({"test_set_id": 1, "case_key": "c2"})
            svc.delete([c1.id])
        with Session(self.engine) as s:
            self.assertEqual(s.get(WorkflowTestSet, 1).items_count, 1)

    def test_update_case_key_unique_excluding_self(self):
        with Session(self.engine) as s:
            svc = WorkflowTestCaseService(s)
            c1 = svc.add({"test_set_id": 1, "case_key": "c1"})
            svc.add({"test_set_id": 1, "case_key": "c2"})
            # 改成已存在的 c2 → 拒绝
            with self.assertRaises(HTTPException):
                svc.update(WorkflowTestCaseUpdateRequest(id=c1.id, case_key="c2"))
            # 改成自身 c1 → 允许
            svc.update(WorkflowTestCaseUpdateRequest(id=c1.id, case_key="c1", weight=2.0))


if __name__ == "__main__":
    unittest.main()
