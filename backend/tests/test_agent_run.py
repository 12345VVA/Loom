"""agent 会话运行服务测试（P5）：invoke 闭环 / 校验链 / 锁互斥 / SSE 事件序列 / 终态落库。

模型以 FakeChatModel 注入（patch model_wrapper.LoomChatModel——执行线程内 import 时解析）；
发布流依赖真注册表 + 资源层同步（照 test_agent_profile 的装配方式）。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
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
from app.modules.agent.service.runtime import model_wrapper as model_wrapper_module
from app.modules.agent.service.runtime import run_service as run_service_module
from app.modules.agent.service.runtime.run_lock import acquire_run_lock
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _FakeChatModel:
    """执行线程内的模型桩（构造参数兼容 LoomChatModel；generate 返回固定回答）。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def generate(self, messages, **kwargs):
        return LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="测试回答"))]],
            llm_output={"usage": {"totalTokens": 50}},
        )


class RunFlowTestCase(unittest.TestCase):
    """invoke 闭环 + 校验链 + 终态落库（Fake 模型；published 真快照流）。"""

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
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        sync_resources(self.session)
        self.service = AgentProfileService(self.session)
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.profile = self.service.add(
            AgentProfileCreateRequest(name="运行测试", model_profile_code="deepseek-chat", tools=["current_time"]),
            current_user=self.owner,
        )
        self.service.publish(self.profile.id, current_user=self.owner)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _invoke(self, question="你好", session_id=None, user=None, run_mode="published", profile_id=None):
        svc = AgentRunService(self.session)
        with patch.object(model_wrapper_module, "LoomChatModel", _FakeChatModel):  # 执行线程内 import 解析源
            return svc.invoke_run(
                profile_id=profile_id or self.profile.id,
                session_id=session_id,
                question=question,
                run_mode=run_mode,
                current_user=user or self.owner,
            )

    def test_invoke_completes_and_persists(self):
        """验收 1/14：published 快照运行 → completed 终态 + 三处口径一致（trace/消息/事件）。"""
        result = self._invoke()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["payload"]["answer"], "测试回答")

        self.session.expire_all()  # StaticPool 单连接：结束请求线程事务后读工作线程写入
        trace = self.session.exec(
            select(AgentRunTrace).where(AgentRunTrace.run_mode == "published").order_by(AgentRunTrace.id.desc())
        ).first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.status, "completed")
        self.assertEqual(trace.run_mode, "published")
        self.assertIsNotNone(trace.snapshot_id)
        self.assertEqual(trace.model_calls, 1)
        self.assertGreaterEqual(trace.duration_ms, 0)  # Fake 模型亚毫秒完成会被 int 截断为 0

        messages = self.session.exec(
            select(AgentMessage).where(AgentMessage.session_id == result["sessionId"]).order_by(AgentMessage.id)
        ).all()
        self.assertEqual([m.role for m in messages], ["user", "assistant"])
        self.assertEqual(messages[0].content, "你好")
        self.assertEqual(messages[1].content, "测试回答")

        # 锁已释放：同会话可立即再次发起
        second = self._invoke(question="再来", session_id=result["sessionId"])
        self.assertEqual(second["status"], "completed")

    def test_session_reuse_same_run_mode(self):
        """同一 published 会话可延续（每轮用当时当前快照——跨版本规则依赖 trace.snapshot_id）。"""
        first = self._invoke()
        second = self._invoke(question="第二轮", session_id=first["sessionId"])
        self.assertEqual(first["sessionId"], second["sessionId"])

    def test_unpublished_rejected(self):
        """published 请求但无快照 → 明确拒绝。"""
        fresh = self.service.add(
            AgentProfileCreateRequest(name="未发布", model_profile_code="deepseek-chat", tools=["current_time"]),
            current_user=self.owner,
        )
        with self.assertRaises(HTTPException) as ctx:
            self._invoke(profile_id=fresh.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("尚未发布", ctx.exception.detail)

    def test_disabled_profile_rejected(self):
        """D14 实时启停：停用后新 run 被拒（发布快照不豁免）。"""
        self.service.toggle_enabled(self.profile.id, False, current_user=self.owner)
        with self.assertRaises(HTTPException) as ctx:
            self._invoke()
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("停用", ctx.exception.detail)

    def test_session_owner_enforced(self):
        """对象级权限：他人不可借用本人 session_id（验收 21）。"""
        result = self._invoke()
        with self.assertRaises(HTTPException) as ctx:
            self._invoke(session_id=result["sessionId"], user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_run_mode_isolation(self):
        """draft/published 会话互不可复用（评审 P0-5 隔离）。"""
        published = self._invoke()
        with self.assertRaises(HTTPException) as ctx:
            self._invoke(session_id=published["sessionId"], run_mode="draft")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("运行模式", ctx.exception.detail)

    def test_lock_rejects_concurrent_run(self):
        """同会话串行锁：持锁期间新 run 409（验收 ②的单元面）。"""
        assert acquire_run_lock(self.profile.id, "other-token", timeout_seconds=60) is True
        try:
            with self.assertRaises(HTTPException) as ctx:
                self._invoke()
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("尚未结束", ctx.exception.detail)
        finally:
            from app.modules.agent.service.runtime.run_lock import release_run_lock

            release_run_lock(self.profile.id, "other-token")

    def test_debug_chat_draft_flow(self):
        """debugChat（draft）：草稿载荷直接运行（调试台永远最新草稿，评审 P1-1）。"""
        result = self._invoke(run_mode="draft")
        self.assertEqual(result["status"], "completed")
        trace = self.session.exec(select(AgentRunTrace).where(AgentRunTrace.run_mode == "draft")).first()
        self.assertIsNotNone(trace)
        self.assertIsNone(trace.snapshot_id)  # draft 无快照

    def test_stop_unknown_token_is_noop(self):
        svc = AgentRunService(self.session)
        result = svc.stop_run("no-such-token", self.owner)
        self.assertFalse(result["stopped"])


class SseFrameTestCase(unittest.TestCase):
    """SSE 帧形态（复用 ai 先例；parseSse 消费）。"""

    def test_sse_frame_shape(self):
        frame = run_service_module.sse_frame("final", {"answer": "ok"})
        self.assertTrue(frame.startswith("data: "))
        self.assertTrue(frame.endswith("\n\n"))
        self.assertIn('"type": "final"', frame)
        self.assertEqual(run_service_module.HEARTBEAT_FRAME, ": ping\n\n")

    def test_run_handle_closes_once(self):
        """终态后事件出口永久关闭（评审 P1-4）：close 后 emit 丢弃、队列恰一哨兵。"""
        handle = run_service_module.RunHandle(1, "tok", 2, run_service_module.RunDeadline(30))
        handle.close("final", {"answer": "done"})
        handle.emit("tool_started", {})  # 必须被丢弃
        events = []
        while True:
            event = handle.event_queue.get(timeout=1)
            if event is None:
                break
            events.append(event.type)
        self.assertEqual(events, ["final"])
        self.assertTrue(handle.closed)


if __name__ == "__main__":
    unittest.main()
