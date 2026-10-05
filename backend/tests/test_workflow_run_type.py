"""工作流实例 run_type 治理测试（P0-2/P0-3：正式/试运行/评估边界隔离）。

- start_instance → production；start_trial_instance → trial
- create_eval_instance → eval + eval_run_id 回填
- 产物打标：persist_workflow_artifacts 冗余实例 run_type
- is_test property 与 Read DTO runType 透传
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import Mock, patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.modules.base.model.auth import User
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
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


class NodeTestPersistTestCase(unittest.TestCase):
    """P1-4 落库：test_node 建 run_type='test_node' 实例 + 单行执行日志。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        # 草稿版 graph：含一个可测节点（type 任意，executor 由测试 patch）
        graph = json.dumps({"nodes": [{"id": "n1", "type": "llm", "name": "测试节点", "config": {}}], "edges": []})
        from app.modules.workflow.model.workflow_version import (
            WorkflowDefinitionVersion,
            WorkflowVersionStatus,
        )

        definition = WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1)
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        draft = WorkflowDefinitionVersion(
            definition_id=definition.id,
            version_no=1,
            status=WorkflowVersionStatus.DRAFT,
            graph_json=graph,
            user_id=1,
        )
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        definition.draft_version_id = draft.id
        self.session.add(definition)
        self.session.commit()
        self.def_id = definition.id
        self.draft_vid = draft.id

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _run_test_node(self, executor):
        """统一驱动：patch registry/redis 后执行 test_node，返回 (响应, 实例, 日志行)。"""
        from app.modules.workflow.service import compiler as compiler_mod
        from app.modules.workflow.service.workflow_service import WorkflowInstanceService

        svc = WorkflowInstanceService(self.session)
        with (
            patch.object(compiler_mod.node_registry, "get", return_value=executor),
            patch("app.core.redis.redis_client") as mock_redis,
        ):
            mock_redis.set.return_value = True
            resp = asyncio.run(svc.test_node(self.def_id, "n1", {"q": "hi"}, _user(1)))
        instance = self.session.exec(
            select(WorkflowInstance).where(WorkflowInstance.definition_id == self.def_id)
        ).first()
        log_row = self.session.exec(
            select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == instance.id)
        ).first()
        return resp, instance, log_row

    def test_success_persists_instance_and_log(self):
        async def ok(inputs, config):
            return {"answer": "ok"}

        resp, instance, log_row = self._run_test_node(ok)
        self.assertEqual(instance.run_type, "test_node")
        self.assertTrue(instance.is_test)
        self.assertEqual(instance.version_id, self.draft_vid)  # 跑草稿版
        self.assertEqual(instance.status, "success")
        self.assertIsNone(instance.error_message)
        self.assertEqual(resp.instance_id, instance.id)  # 响应透传实例 ID
        self.assertIsNotNone(log_row)
        self.assertEqual(log_row.node_name, "测试节点")
        self.assertEqual(log_row.status, "success")
        self.assertIn('"q"', log_row.input_data)  # mock 输入入日志
        self.assertIn("ok", log_row.output_data)

    def test_failure_persists_error_state(self):
        async def boom(inputs, config):
            raise RuntimeError("节点炸了")

        resp, instance, log_row = self._run_test_node(boom)
        self.assertEqual(instance.status, "failed")
        self.assertIn("节点炸了", instance.error_message)
        self.assertEqual(log_row.status, "error")
        self.assertEqual(resp.error, instance.error_message)


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
