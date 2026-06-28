"""工作流版本管理与发布管理测试。

覆盖 WorkflowVersionService：save_draft（新建/覆盖/拓扑校验）、publish（CAS 状态机+自动新草稿）、
rollback（复制目标为新草稿）、diff（结构对比）、owner 越权校验、start_instance 写 version_id、
version_no 递增与唯一约束。
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import WorkflowDefinition
from app.modules.workflow.model.workflow_version import (
    WorkflowDefinitionVersion,
    WorkflowVersionStatus,
)
from app.modules.workflow.service.workflow_service import WorkflowInstanceService
from app.modules.workflow.service.workflow_version_service import WorkflowVersionService


def _user(uid: int, super_admin: bool = False) -> User:
    return User(
        id=uid, username=f"u{uid}", full_name=f"u{uid}", password_hash="x", is_active=True, is_super_admin=super_admin
    )


def _graph(base: int = 0, nodes: int = 1, edges: int = 0) -> str:
    return json.dumps(
        {
            "nodes": [{"id": f"n{i}", "type": "test", "name": f"N{i}", "config": {"k": base + i}} for i in range(nodes)],
            "edges": [{"source": f"n{i}", "target": f"n{i + 1}", "type": "default"} for i in range(edges)],
        }
    )


class VersioningTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1))
        self.session.commit()
        self.def_id = self.session.exec(select(WorkflowDefinition)).first().id

    def tearDown(self):
        self.session.close()

    def _svc(self) -> WorkflowVersionService:
        return WorkflowVersionService(self.session)

    # --------------------------------- save_draft ---------------------------------

    def test_save_draft_creates_first_draft(self):
        version = self._svc().save_draft(self.def_id, _graph(), current_user=_user(1))
        self.assertEqual(version.status, WorkflowVersionStatus.DRAFT)
        self.assertEqual(version.version_no, 1)
        d = self.session.get(WorkflowDefinition, self.def_id)
        self.assertEqual(d.draft_version_id, version.id)
        self.assertIsNone(d.current_version_id)  # 尚未发布

    def test_save_draft_overwrites_existing_draft(self):
        svc = self._svc()
        v1 = svc.save_draft(self.def_id, _graph(base=1), current_user=_user(1))
        v2 = svc.save_draft(self.def_id, _graph(base=2), current_user=_user(1))
        self.assertEqual(v1.id, v2.id)  # 同一草稿，覆盖而非新建
        draft = self.session.get(WorkflowDefinitionVersion, v1.id)
        self.assertEqual(json.loads(draft.graph_json)["nodes"][0]["config"]["k"], 2)

    def test_save_draft_rejects_invalid_graph(self):
        with self.assertRaises(HTTPException) as cm:
            self._svc().save_draft(self.def_id, "{not json", current_user=_user(1))
        self.assertEqual(cm.exception.status_code, 400)

    def test_save_draft_rejects_non_owner(self):
        with self.assertRaises(HTTPException) as cm:
            self._svc().save_draft(self.def_id, _graph(), current_user=_user(2))
        self.assertEqual(cm.exception.status_code, 403)

    # --------------------------------- publish ---------------------------------

    def test_publish_promotes_draft_and_archives_old(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(1), current_user=_user(1))
        pub1 = svc.publish(self.def_id, "first", current_user=_user(1))
        self.assertEqual(pub1.status, WorkflowVersionStatus.PUBLISHED)
        d = self.session.get(WorkflowDefinition, self.def_id)
        self.assertEqual(d.current_version_id, pub1.id)
        self.assertIsNotNone(d.draft_version_id)  # publish 自动建新草稿
        new_draft = self.session.get(WorkflowDefinitionVersion, d.draft_version_id)
        self.assertEqual(new_draft.status, WorkflowVersionStatus.DRAFT)
        self.assertEqual(new_draft.parent_version_id, pub1.id)

        # 二次发布：旧 published → archived
        svc.save_draft(self.def_id, _graph(2), current_user=_user(1))
        pub2 = svc.publish(self.def_id, "second", current_user=_user(1))
        self.assertEqual(self.session.get(WorkflowDefinitionVersion, pub1.id).status, WorkflowVersionStatus.ARCHIVED)
        self.assertEqual(pub2.status, WorkflowVersionStatus.PUBLISHED)
        self.assertEqual(self.session.get(WorkflowDefinition, self.def_id).current_version_id, pub2.id)

    def test_publish_without_draft_returns_400(self):
        with self.assertRaises(HTTPException) as cm:
            self._svc().publish(self.def_id, None, current_user=_user(1))
        self.assertEqual(cm.exception.status_code, 400)

    # --------------------------------- rollback ---------------------------------

    def test_rollback_copies_target_to_draft(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(base=1), current_user=_user(1))
        pub1 = svc.publish(self.def_id, "v1", current_user=_user(1))
        svc.save_draft(self.def_id, _graph(base=5), current_user=_user(1))
        svc.publish(self.def_id, "v2", current_user=_user(1))
        # 回滚到 v1
        svc.rollback(self.def_id, pub1.id, None, current_user=_user(1), immediate=False)
        d = self.session.get(WorkflowDefinition, self.def_id)
        draft = self.session.get(WorkflowDefinitionVersion, d.draft_version_id)
        self.assertEqual(json.loads(draft.graph_json)["nodes"][0]["config"]["k"], 1)  # 内容=v1
        self.assertEqual(draft.parent_version_id, pub1.id)

    # --------------------------------- diff ---------------------------------

    def test_diff_detects_added_removed_modified(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(nodes=2, edges=1), current_user=_user(1))
        pub1 = svc.publish(self.def_id, "v1", current_user=_user(1))
        new_graph = json.dumps(
            {
                "nodes": [
                    {"id": "n0", "type": "test", "config": {"k": 99}},
                    {"id": "n2", "type": "test", "config": {"k": 2}},
                ],
                "edges": [],
            }
        )
        svc.save_draft(self.def_id, new_graph, current_user=_user(1))
        pub2 = svc.publish(self.def_id, "v2", current_user=_user(1))
        diff = svc.diff(pub1.id, pub2.id, current_user=_user(1))
        self.assertIn("n2", [n["id"] for n in diff["nodesAdded"]])
        self.assertIn("n1", [n["id"] for n in diff["nodesRemoved"]])
        self.assertIn("n0", [n["id"] for n in diff["nodesModified"]])

    def test_diff_rejects_non_owner(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(), current_user=_user(1))
        pub = svc.publish(self.def_id, "v1", current_user=_user(1))
        with self.assertRaises(HTTPException) as cm:
            svc.diff(pub.id, pub.id, current_user=_user(2))
        self.assertEqual(cm.exception.status_code, 403)

    # --------------------------------- version_no ---------------------------------

    def test_version_no_increments_monotonically(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(), current_user=_user(1))
        svc.publish(self.def_id, "v1", current_user=_user(1))
        svc.save_draft(self.def_id, _graph(), current_user=_user(1))
        svc.publish(self.def_id, "v2", current_user=_user(1))
        version_nos = [
            v.version_no
            for v in self.session.exec(
                select(WorkflowDefinitionVersion)
                .where(WorkflowDefinitionVersion.definition_id == self.def_id)
                .order_by(WorkflowDefinitionVersion.version_no)
            ).all()
        ]
        # v1 published(1) → draft(2) → published(2) → draft(3)
        self.assertEqual(version_nos, [1, 2, 3])

    # --------------------------------- start_instance ---------------------------------

    def test_start_instance_writes_version_id(self):
        svc = self._svc()
        svc.save_draft(self.def_id, _graph(), current_user=_user(1))
        pub = svc.publish(self.def_id, "v1", current_user=_user(1))
        inst_svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value = Mock(id="task-1")
            instance = inst_svc.start_instance(self.def_id, {"q": "hi"}, _user(7))
        self.assertEqual(instance.version_id, pub.id)


if __name__ == "__main__":
    unittest.main()
