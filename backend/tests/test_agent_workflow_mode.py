"""智能体编排模式测试（E17）：发布校验链 / workflow 运行分支 / 取消与实时校验 / 调试台拒绝。

工作流执行以 patch execute_workflow.delay 注入终态（不派发 Celery）——start_instance 真实路径
（建 pending 实例 + 去重 + 回链），run 线程轮询自然收敛；编排模式无模型调用，无需模型桩。
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine, seed_chat_channel
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AgentMessage,
    AgentProfile,
    AgentProfileCreateRequest,
    AgentProfileDraft,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
    AgentRunTrace,
    AgentSession,
    AgentToolCallLog,
    AgentToolResource,
)
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance

_AI_CHANNEL_TABLES = [AiProvider.__table__, AiModel.__table__, AiModelProfile.__table__]
# workflow 侧最小表集（start_instance 只写 definition/instance 两表；version 表不触）
_WORKFLOW_TABLES = [WorkflowDefinition.__table__, WorkflowInstance.__table__]

WORKFLOW_PUBLISH_VERSION_ID = 501


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _FakeDelayTask:
    """start_instance 对 delay 返回值回写 celery_task_id——桩需返回带 id 的对象。"""

    id = "test-celery-task"


def _finish_instance(engine, instance_id: int, status: str, output=None, error: str | None = None) -> None:
    """模拟工作流执行终态（替代 Celery worker）：置 state_data/status——run 线程轮询由此收敛。"""
    with Session(engine) as session:
        instance = session.get(WorkflowInstance, instance_id)
        instance.status = status
        if output is not None:
            instance.state_data = json.dumps({"workflow_output": output}, ensure_ascii=False)
        if error:
            instance.error_message = error
        session.add(instance)
        session.commit()


class WorkflowModeTestCase(unittest.TestCase):
    """发布校验链 + invoke 运行分支（E17）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentSession.__table__,
                AgentMessage.__table__,
                AgentRunTrace.__table__,
                AgentToolCallLog.__table__,
                AgentToolResource.__table__,
                *_AI_CHANNEL_TABLES,
                *_WORKFLOW_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        # 渠道窗口未知（None）：编排模式发布/运行应跳过 E15 窗口断言（渠道不参与执行）
        seed_chat_channel(self.engine, context_window=None)
        sync_resources(self.session)
        self.service = AgentProfileService(self.session)
        self.owner = _FakeUser(1)
        self.workflow = self._seed_workflow()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _seed_workflow(
        self, *, code: str = "wf-orchestrate", is_active: bool = True, published: bool = True
    ) -> WorkflowDefinition:
        row = WorkflowDefinition(
            code=code,
            name="编排工作流",
            is_active=is_active,
            current_version_id=WORKFLOW_PUBLISH_VERSION_ID if published else None,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def _add_profile(self, *, execution_mode: str = "workflow", workflow_definition_id: int | None = None):
        return self.service.add(
            AgentProfileCreateRequest(
                name="编排智能体",
                model_profile_code="deepseek-chat",
                tools=["current_time"],
                execution_mode=execution_mode,
                workflow_definition_id=workflow_definition_id,
            ),
            current_user=self.owner,
        )

    # ---------------- 发布校验 ----------------

    def test_publish_requires_binding(self):
        profile = self._add_profile(execution_mode="workflow", workflow_definition_id=None)
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("必须绑定工作流", str(ctx.exception.detail))

    def test_publish_rejects_unpublished_workflow(self):
        wf = self._seed_workflow(code="wf-draft-only", published=False)
        profile = self._add_profile(workflow_definition_id=wf.id)
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("尚未发布任何版本", str(ctx.exception.detail))

    def test_publish_rejects_inactive_workflow(self):
        wf = self._seed_workflow(code="wf-disabled", is_active=False)
        profile = self._add_profile(workflow_definition_id=wf.id)
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("已停用", str(ctx.exception.detail))

    def test_publish_workflow_snapshot_carries_binding_and_skips_window(self):
        """正常绑定：快照 execution 段含引用与版本摘要；渠道窗口未知（None）不拦发布（E15 跳过）。"""
        profile = self._add_profile(workflow_definition_id=self.workflow.id)
        snapshot = self.service.publish(profile.id, current_user=self.owner)
        payload = json.loads(snapshot.snapshot_json)
        execution = payload["execution"]
        self.assertEqual(execution["mode"], "workflow")
        self.assertEqual(execution["workflowDefinitionId"], self.workflow.id)
        self.assertEqual(
            execution["workflowSummary"],
            {"code": "wf-orchestrate", "name": "编排工作流", "versionId": WORKFLOW_PUBLISH_VERSION_ID},
        )

    def test_chat_mode_snapshot_defaults_and_window_still_enforced(self):
        """chat 型回归：execution.mode=chat；窗口未知渠道照旧拒绝发布（E15 不受 E17 影响）。"""
        profile = self._add_profile(execution_mode="chat", workflow_definition_id=None)
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("未知窗口", str(ctx.exception.detail))

    # ---------------- 运行分支 ----------------

    def _invoke(self, profile, user=None):
        svc = AgentRunService(self.session)

        def _dispatch_and_finish(instance_id, definition_id, inputs_json):
            # 替代 Celery worker：真实 start_instance 落 pending 实例后，直接置终态
            _finish_instance(self.engine, instance_id, "success", output="编排结果文本")
            return _FakeDelayTask()

        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow.delay", _dispatch_and_finish):
            return svc.invoke_run(
                profile_id=profile.id,
                session_id=None,
                question="帮我编排一下",
                run_mode="published",
                current_user=user or self.owner,
            )

    def test_invoke_workflow_run_completes(self):
        """编排 run：success 输出回写 assistant 消息 + trace 回链 instance + final 口径。"""
        profile = self._add_profile(workflow_definition_id=self.workflow.id)
        self.service.publish(profile.id, current_user=self.owner)

        result = self._invoke(profile)
        self.session.expire_all()  # StaticPool 双 Session：执行线程已提交，测试 Session 缓存需失效（一期坑③）
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["payload"]["answer"], "编排结果文本")
        self.assertEqual(result["payload"]["modelCalls"], 0)
        self.assertGreater(result["payload"]["workflowInstanceId"], 0)

        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertEqual(trace.status, "completed")
        self.assertEqual(trace.workflow_instance_id, result["payload"]["workflowInstanceId"])
        self.assertIsNone(trace.guardrails_version)  # D16：编排型不经 LLM 护栏，不记版本
        messages = self.session.exec(select(AgentMessage).order_by(AgentMessage.id)).all()  # type: ignore[attr-defined]
        self.assertEqual([m.role for m in messages], ["user", "assistant"])
        self.assertEqual(messages[-1].content, "编排结果文本")

    def test_invoke_workflow_failure_propagates(self):
        profile = self._add_profile(workflow_definition_id=self.workflow.id)
        self.service.publish(profile.id, current_user=self.owner)

        def _dispatch_failed(instance_id, definition_id, inputs_json):
            _finish_instance(self.engine, instance_id, "failed", error="LLM 节点超限")
            return _FakeDelayTask()

        with patch("app.modules.workflow.tasks.workflow_tasks.execute_workflow.delay", _dispatch_failed):
            result = AgentRunService(self.session).invoke_run(
                profile_id=profile.id,
                session_id=None,
                question="你好",
                run_mode="published",
                current_user=self.owner,
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("LLM 节点超限", result["payload"].get("message", ""))
        self.session.expire_all()
        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertEqual(trace.status, "failed")
        self.assertIn("LLM 节点超限", trace.error or "")

    def test_invoke_rejects_when_workflow_disabled_after_publish(self):
        """D14 实时安全约束高于快照：发布后工作流被停用 → run 拒绝（快照不豁免）。"""
        profile = self._add_profile(workflow_definition_id=self.workflow.id)
        self.service.publish(profile.id, current_user=self.owner)

        self.workflow.is_active = False
        self.session.add(self.workflow)
        self.session.commit()

        result = self._invoke(profile)
        self.assertEqual(result["status"], "failed")
        self.assertIn("已停用", result["payload"].get("message", ""))
        self.session.expire_all()

    def test_debug_chat_rejects_workflow_profile(self):
        """编排型草稿不支持调试台试聊（draft 链路无 workflow 执行语义）。"""
        profile = self._add_profile(workflow_definition_id=self.workflow.id)
        with self.assertRaises(HTTPException) as ctx:
            AgentRunService(self.session).invoke_run(
                profile_id=profile.id,
                session_id=None,
                question="你好",
                run_mode="draft",
                current_user=self.owner,
            )
        self.assertIn("不支持调试台试聊", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
