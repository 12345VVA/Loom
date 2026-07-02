"""工作流定义编码自动生成测试。

覆盖 WorkflowService._before_add：code 缺省时自动生成（WF+YYYYMMDD+3位序列，唯一）；
显式传入 code 仍生效并校验唯一。
"""

from __future__ import annotations

import re
import unittest

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow.model.workflow import WorkflowDefinitionCreateRequest
from app.modules.workflow.service.workflow_service import WorkflowService


CODE_RE = re.compile(r"^WF\d{8}\d{3}$")


class DefinitionCodeTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _svc(self) -> WorkflowService:
        return WorkflowService(self.session)

    def test_add_generates_code_when_missing(self):
        entity = self._svc().add(WorkflowDefinitionCreateRequest(name="Auto1"))
        self.assertIsNotNone(entity.code)
        self.assertRegex(entity.code, CODE_RE)

    def test_generated_codes_are_unique(self):
        svc = self._svc()
        a = svc.add(WorkflowDefinitionCreateRequest(name="A"))
        b = svc.add(WorkflowDefinitionCreateRequest(name="B"))
        self.assertNotEqual(a.code, b.code)
        self.assertRegex(a.code, CODE_RE)
        self.assertRegex(b.code, CODE_RE)

    def test_explicit_code_is_respected(self):
        entity = self._svc().add(WorkflowDefinitionCreateRequest(code="my_code", name="C"))
        self.assertEqual(entity.code, "my_code")

    def test_duplicate_explicit_code_rejected(self):
        svc = self._svc()
        svc.add(WorkflowDefinitionCreateRequest(code="dup", name="D1"))
        with self.assertRaises(HTTPException) as cm:
            svc.add(WorkflowDefinitionCreateRequest(code="dup", name="D2"))
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
