"""工作流模块数据所有者隔离测试（修复审查报告 S1 IDOR）。

覆盖：
- WorkflowDefinition 新增自动写入 user_id
- update / delete 越权拒绝（403），owner / 超管放行
- owner_id 为 None 的旧数据兼容放行
- WorkflowInstance start 写入 user_id、resume / testNode 越权拒绝
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionUpdateRequest,
    WorkflowInstance,
)
from app.modules.workflow.service.workflow_service import (
    WorkflowInstanceService,
    WorkflowService,
)


def _user(uid: int, super_admin: bool = False) -> User:
    return User(
        id=uid,
        username=f"u{uid}",
        full_name=f"u{uid}",
        password_hash="x",
        is_active=True,
        is_super_admin=super_admin,
    )


class WorkflowOwnerTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self, code: str = "wf1", owner_uid: int | None = None) -> WorkflowDefinition:
        from app.modules.workflow.model.workflow_version import (
            WorkflowDefinitionVersion,
            WorkflowVersionStatus,
        )

        definition = WorkflowDefinition(code=code, name=code.upper(), is_active=True, user_id=owner_uid)
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        # 建一个 published + draft 版本并设指针，让 start_instance / test_node 可用
        graph = '{"nodes":[],"edges":[]}'
        pub = WorkflowDefinitionVersion(
            definition_id=definition.id,
            version_no=1,
            status=WorkflowVersionStatus.PUBLISHED,
            graph_json=graph,
            user_id=owner_uid,
        )
        self.session.add(pub)
        self.session.commit()
        self.session.refresh(pub)
        draft = WorkflowDefinitionVersion(
            definition_id=definition.id,
            version_no=2,
            status=WorkflowVersionStatus.DRAFT,
            graph_json=graph,
            parent_version_id=pub.id,
            user_id=owner_uid,
        )
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        definition.current_version_id = pub.id
        definition.draft_version_id = draft.id
        self.session.add(definition)
        self.session.commit()
        return definition

    # --- WorkflowDefinition CRUD ---

    def test_add_writes_user_id(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(5),
        )
        self.assertEqual(definition.user_id, 5)

    def test_add_without_user_has_null_owner(self):
        svc = WorkflowService(self.session)
        definition = svc.add({"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True})
        self.assertIsNone(definition.user_id)

    def test_update_rejects_non_owner(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(1),
        )
        with self.assertRaises(HTTPException) as cm:
            svc.update(WorkflowDefinitionUpdateRequest(id=definition.id, name="hacked"), current_user=_user(2))
        self.assertEqual(cm.exception.status_code, 403)
        # 原名未被修改
        self.assertEqual(self.session.get(WorkflowDefinition, definition.id).name, "WF1")

    def test_update_allows_owner(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(1),
        )
        svc.update(WorkflowDefinitionUpdateRequest(id=definition.id, name="renamed"), current_user=_user(1))
        self.assertEqual(self.session.get(WorkflowDefinition, definition.id).name, "renamed")

    def test_update_allows_super_admin(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(1),
        )
        svc.update(
            WorkflowDefinitionUpdateRequest(id=definition.id, name="admin-renamed"),
            current_user=_user(99, super_admin=True),
        )
        self.assertEqual(self.session.get(WorkflowDefinition, definition.id).name, "admin-renamed")

    def test_update_allows_legacy_null_owner(self):
        """迁移前的旧数据 user_id 为 None，任何用户均可操作（兼容期）。"""
        definition = self._add_definition(owner_uid=None)
        svc = WorkflowService(self.session)
        svc.update(WorkflowDefinitionUpdateRequest(id=definition.id, name="claimed"), current_user=_user(2))
        self.assertEqual(self.session.get(WorkflowDefinition, definition.id).name, "claimed")

    def test_delete_rejects_non_owner(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(1),
        )
        with self.assertRaises(HTTPException) as cm:
            svc.delete([definition.id], current_user=_user(2))
        self.assertEqual(cm.exception.status_code, 403)

    def test_delete_allows_owner(self):
        svc = WorkflowService(self.session)
        definition = svc.add(
            {"code": "wf1", "name": "WF1", "graph_json": "{}", "is_active": True},
            current_user=_user(1),
        )
        svc.delete([definition.id], current_user=_user(1), soft_delete=True)
        # 软删除：delete_time 被置
        self.assertIsNotNone(self.session.get(WorkflowDefinition, definition.id).delete_time)

    # --- WorkflowInstance 自定义接口 ---

    def test_start_instance_writes_user_id(self):
        definition = self._add_definition(owner_uid=1)
        svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value = Mock(id="task-1")
            instance = svc.start_instance(definition.id, {"q": "hi"}, _user(7))
        self.assertEqual(instance.user_id, 7)

    def test_resume_rejects_non_owner(self):
        instance = WorkflowInstance(definition_id=999, thread_id="t1", status="paused", user_id=1)
        self.session.add(instance)
        self.session.commit()
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            svc.resume_instance(instance.id, "ok", current_user=_user(2))
        self.assertEqual(cm.exception.status_code, 403)

    def test_test_node_rejects_non_owner(self):
        definition = self._add_definition(owner_uid=1)
        svc = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(svc.test_node(definition.id, "n1", {}, current_user=_user(2)))
        self.assertEqual(cm.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
