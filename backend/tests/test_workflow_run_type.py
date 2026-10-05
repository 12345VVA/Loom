"""工作流实例 run_type 治理测试（P0-2/P0-3：正式/试运行/评估边界隔离）。

- start_instance → production；start_trial_instance → trial
- create_eval_instance → eval + eval_run_id 回填
- 产物打标：persist_workflow_artifacts 冗余实例 run_type
- is_test property 与 Read DTO runType 透传
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowInstanceRead,
)
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact
from app.modules.workflow.service.artifact_service import persist_workflow_artifacts
from app.modules.workflow.service.workflow_service import WorkflowInstanceService
from app.modules.workflow.service.workflow_version_service import WorkflowVersionService
from app.modules.workflow_eval.model.test_set import WorkflowTestCase
from app.modules.workflow_eval.service.eval_orchestrator import create_eval_instance


def _user(uid: int) -> User:
    return User(id=uid, username=f"u{uid}", full_name=f"u{uid}", password_hash="x", is_active=True)


def _graph() -> str:
    return json.dumps({"nodes": [{"id": "n0", "type": "test", "name": "N0", "config": {}}], "edges": []})


class RunTypeInstanceTestCase(unittest.TestCase):
    """建实例入口打标：正式/试运行/评估。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1))
        self.session.commit()
        self.def_id = self.session.exec(select(WorkflowDefinition)).first().id

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_start_instance_is_production(self):
        WorkflowVersionService(self.session).save_draft(self.def_id, _graph(), current_user=_user(1))
        WorkflowVersionService(self.session).publish(self.def_id, "v1", current_user=_user(1))

        inst_svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value = Mock(id="task-1")
            instance = inst_svc.start_instance(self.def_id, {"q": "hi"}, _user(7))
        self.assertEqual(instance.run_type, "production")
        self.assertFalse(instance.is_test)
        self.assertIsNone(instance.eval_run_id)

    def test_start_trial_instance_is_trial(self):
        WorkflowVersionService(self.session).save_draft(self.def_id, _graph(), current_user=_user(1))

        inst_svc = WorkflowInstanceService(self.session)
        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow") as mock_exec:
            mock_exec.delay.return_value = Mock(id="task-trial")
            instance = inst_svc.start_trial_instance(self.def_id, {"q": "hi"}, _user(7))
        self.assertEqual(instance.run_type, "trial")
        self.assertTrue(instance.is_test)

    def test_create_eval_instance_is_eval_with_run_id(self):
        case = WorkflowTestCase(test_set_id=1, case_key="c1", input_data='{"q": "hi"}')
        with patch("app.modules.workflow_eval.service.eval_orchestrator.engine", self.engine):
            instance_id = create_eval_instance(self.def_id, None, case, user_id=7, eval_run_id=42)
        instance = self.session.get(WorkflowInstance, instance_id)
        self.assertEqual(instance.run_type, "eval")
        self.assertTrue(instance.is_test)
        self.assertEqual(instance.eval_run_id, 42)

    def test_read_dto_transpares_run_type(self):
        instance = WorkflowInstance(definition_id=self.def_id, thread_id="t1", status="running", state_data="{}")
        self.session.add(instance)
        self.session.commit()
        dto = WorkflowInstanceRead.model_validate(instance)
        dumped = dto.model_dump(by_alias=True)
        self.assertEqual(dumped["runType"], "production")
        self.assertIsNone(dumped["evalRunId"])


class ArtifactRunTypeMarkTestCase(unittest.TestCase):
    """产物打标：测试实例的产物冗余 run_type，可区分/批量清理。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _seed_instance(self, run_type: str) -> int:
        with Session(self.engine) as session:
            definition = WorkflowDefinition(code=f"wf_{run_type}", name="wf", is_active=True, user_id=1)
            session.add(definition)
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id, thread_id="t1", status="success", state_data="{}", run_type=run_type
            )
            session.add(instance)
            session.commit()
            return instance.id

    def test_artifact_marks_run_type_following_instance(self):
        for run_type in ("production", "trial", "eval"):
            with self.subTest(run_type=run_type):
                instance_id = self._seed_instance(run_type)
                persist_workflow_artifacts(
                    instance_id, 1, None, 1, None, {"report": "测试产物内容"}, engine=self.engine
                )
                with Session(self.engine) as session:
                    artifacts = session.exec(
                        select(WorkflowArtifact).where(WorkflowArtifact.instance_id == instance_id)
                    ).all()
                self.assertTrue(artifacts)
                for art in artifacts:
                    self.assertEqual(art.run_type, run_type)

    def test_artifact_defaults_production_when_instance_missing(self):
        """实例缺失（异常兜底场景）按 production 处理，不报错。"""
        persist_workflow_artifacts(999999, 1, None, 1, None, {"report": "孤儿产物"}, engine=self.engine)
        with Session(self.engine) as session:
            artifacts = session.exec(select(WorkflowArtifact).where(WorkflowArtifact.instance_id == 999999)).all()
        for art in artifacts:
            self.assertEqual(art.run_type, "production")


if __name__ == "__main__":
    unittest.main()
