"""agent 会话运行服务测试（P5）：invoke 闭环 / 校验链 / 锁互斥 / SSE 事件序列 / 终态落库。

模型以 FakeChatModel 注入（patch model_wrapper.LoomChatModel——执行线程内 import 时解析）；
发布流依赖真注册表 + 资源层同步（照 test_agent_profile 的装配方式）。
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine, seed_chat_channel
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
    AgentToolApproval,
    AgentToolCallLog,
    AgentToolResource,
    AgentToolResourceVersion,
)
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime import model_wrapper as model_wrapper_module
from app.modules.agent.service.runtime import run_service as run_service_module
from app.modules.agent.service.runtime.run_lock import acquire_run_lock
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog

# E15：run 发起校验依赖渠道窗口元数据
_AI_CHANNEL_TABLES = [AiProvider.__table__, AiModel.__table__, AiModelProfile.__table__]


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _FakeChatModel:
    """执行线程内的模型桩（构造参数兼容 LoomChatModel；generate 返回固定回答）。

    bind_tools 记录入参（装配态断言用）——生产路径无条件调用，桩必须适配而非守卫跳过。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None
        self.bound_schemas: list = []

    def bind_tools(self, tools, **kwargs):
        self.bound_schemas = tools
        return self

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
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                *_AI_CHANNEL_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        seed_chat_channel(self.engine)  # E15：run 发起窗口校验依赖
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

    def test_build_runtime_binds_tools_from_snapshot(self):
        """装配态断言（工具链路专题 P0-1 唯一防回归层）：_build_runtime 无条件
        bind_tools，schema envelope 来自快照（D13 冻结语义）而非当前注册表；
        description 随快照下发。真实 LoomChatModel，不走 Fake。"""
        trace = AgentRunTrace(profile_id=self.profile.id, run_mode="published", user_id=1, session_id=1)
        self.session.add(trace)
        self.session.commit()
        self.session.refresh(trace)

        handle = run_service_module.RunHandle(
            trace_id=trace.id, trace_token="tok-build-1", session_id=1, deadline=run_service_module.RunDeadline(60)
        )
        snapshot_tools = {
            "current_time": {
                "level": "readonly",
                "parameters": {"type": "object", "properties": {"tz": {"type": "string"}}},
                "description": "获取当前时间",
            }
        }
        payload = run_service_module.RunPayload(
            snapshot_tools=snapshot_tools,
            bound_names={"current_time"},
            temperature=0.5,
            max_tokens=1000,
            max_tool_rounds=3,
            timeout_seconds=60,
            system_prompt="你是测试智能体",
            context_token_budget=0,
            context_window_min=None,
            enable_memory=False,
        )
        job = run_service_module.RunJob(
            trace_id=trace.id,
            session_id=1,
            run_mode="published",
            user=run_service_module.RunUser(id=1, name="u1"),
            payload=payload,
        )
        budget = run_service_module.RunBudget(max_tool_rounds=3)
        bundle = run_service_module._build_runtime(
            db=self.session,
            job=job,
            payload=payload,
            trace=trace,
            handle=handle,
            budget=budget,
            should_cancel=lambda: False,
            model_profile_code="deepseek-chat",
            render_user_name="u1",
            stream_answer=False,
        )
        # 绑定态：长度 == 绑定工具数；envelope 形态与内容逐字段来自快照
        self.assertEqual(len(bundle.model._bound_schemas), len(payload.bound_names))
        schema = bundle.model._bound_schemas[0]
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "current_time")
        self.assertEqual(schema["function"]["description"], "获取当前时间")
        self.assertEqual(schema["function"]["parameters"], snapshot_tools["current_time"]["parameters"])
        # N-4：断到最终请求参数——_bound_schemas 非空但 _build_options 漏装 tools 时仍能暴露
        self.assertIn("tools", bundle.model._build_options())
        # 装配产物完整性
        self.assertIsNotNone(bundle.graph)
        self.assertIs(bundle.budget, budget)
        self.assertIs(job.budget, budget)
        self.assertEqual(
            sorted(bundle.executor.bound_names),
            ["current_time"],
        )
        self.assertEqual(list(bundle.executor.snapshot_tools), ["current_time"])

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


class _StreamingRunFakeChatModel:
    """E1 SSE 会话模型桩：轮1 工具决策（流式草稿文本+tool_calls）→ 轮2 最终答案。

    记录每轮收到的上下文 messages，供 A35 断言（被 reset 文本不进后续上下文）。
    """

    seen_contexts: list[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def bind_tools(self, tools, **kwargs):
        # 生产装配无条件接线（工具 schema 下发）；桩无需绑定状态，适配为透传
        return self

    def generate(self, messages, **kwargs):
        raise AssertionError("stream 会话不应走 _generate")

    def generate_streaming(self, messages, on_delta):
        type(self).seen_contexts.append([str(m.content) for m in messages])  # 平铺 list[BaseMessage]
        from langchain_core.outputs import ChatGeneration, ChatResult

        if not any(getattr(m, "tool_call_id", None) for m in messages):
            # 轮1：先吐草稿文本再决定调工具（answer_reset 的触发形态）
            on_delta("让我查查")
            message = AIMessage(
                content="让我查查",
                tool_calls=[{"name": "current_time", "args": {}, "id": "call_1", "type": "tool_call"}],
            )
        else:
            on_delta("现在是")
            on_delta("白天")
            message = AIMessage(content="现在是白天")
        return ChatResult(generations=[ChatGeneration(message=message)], llm_output={"usage": {"totalTokens": 10}})


class StreamingRunTestCase(unittest.TestCase):
    """E1 SSE 会话闭环（A23/A26/A35）：answer_delta/reset 事件序列 + 服务端撤销不落库。"""

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
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                *_AI_CHANNEL_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        seed_chat_channel(self.engine)
        sync_resources(self.session)
        self.service = AgentProfileService(self.session)
        self.owner = _FakeUser(1)
        self.profile = self.service.add(
            AgentProfileCreateRequest(name="流式运行", model_profile_code="deepseek-chat", tools=["current_time"]),
            current_user=self.owner,
        )
        self.service.publish(self.profile.id, current_user=self.owner)
        _StreamingRunFakeChatModel.seen_contexts = []

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _stream(self, question="现在几点"):
        import asyncio

        svc = AgentRunService(self.session)
        with patch.object(model_wrapper_module, "LoomChatModel", _StreamingRunFakeChatModel):
            response = svc.stream_run(
                profile_id=self.profile.id,
                session_id=None,
                question=question,
                run_mode="published",
                current_user=self.owner,
            )

            async def _consume():  # starlette 把同步 generator 包成 async iterator
                return [chunk async for chunk in response.body_iterator]

            frames = asyncio.run(_consume())  # 消费须在 patch 作用域内（worker 线程执行 run）
        events = []
        for frame in frames:
            text = frame.strip() if isinstance(frame, str) else frame.decode().strip()
            if text.startswith("data:"):
                events.append(json.loads(text[5:].strip()))
        return events

    def test_answer_events_and_server_side_reset(self):
        """delta/reset 事件序列正确；被 reset 文本不入消息库、不入后续上下文、final 一致。"""
        events = self._stream()
        types = [e["type"] for e in events]

        # 事件序列：轮1 delta → reset；轮2 delta×2 → done；恰一 final
        self.assertEqual(types.count("answer_reset"), 1)
        self.assertEqual(types.count("answer_done"), 1)
        self.assertEqual(types.count("final"), 1)
        reset_idx = types.index("answer_reset")
        self.assertEqual(types[reset_idx - 1], "answer_delta")  # reset 紧随其轮的 delta
        gen1 = events[reset_idx - 1]["payload"]["generationId"]
        reset = events[reset_idx]["payload"]
        self.assertEqual(reset["generationId"], gen1)
        self.assertEqual(reset["upToSeq"], 1)
        final_event = events[-1]
        self.assertEqual(final_event["payload"]["answer"], "现在是白天")
        # 两轮 generationId 不同（分桶）
        done_payload = events[types.index("answer_done")]["payload"]
        self.assertNotEqual(done_payload["generationId"], gen1)

        self.session.expire_all()
        # A35/A26：被 reset 的「让我查查」不在任何持久化消息；assistant 权威答案唯一
        contents = [m.content for m in self.session.exec(select(AgentMessage)).all()]
        self.assertNotIn("让我查查", "".join(c or "" for c in contents))
        self.assertIn("现在是白天", contents)
        tool_rows = [m for m in self.session.exec(select(AgentMessage)).all() if m.role == "tool"]
        self.assertEqual(len(tool_rows), 1)
        self.assertEqual(tool_rows[0].tool_call_id, "call_1")

        # A35 上下文面：轮2 模型输入不含被 reset 文本（服务端撤销在进入 state 前完成）；
        # 且轮2 输入保持 openai 协议形态（AI(tool_calls) 后紧跟 tool 角色，不展平为 user）
        self.assertEqual(len(_StreamingRunFakeChatModel.seen_contexts), 2)
        self.assertNotIn("让我查查", "".join(_StreamingRunFakeChatModel.seen_contexts[1]))  # 轮2 已不见

        # final 与持久化一致
        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertEqual(trace.status, "completed")


class ContextTokenBudgetTestCase(unittest.TestCase):
    """E15 动态输入预算公式（2026-10-28 调参后口径）：常数上限 24000，
    小窗口按「窗口−输出」自动收紧，下限 1000 防异常小窗口挤负。"""

    def test_budget_formula(self):
        from app.modules.agent.service.runtime.run_service import _context_token_budget

        self.assertEqual(_context_token_budget(None, 4000), 24000)  # None 理论不可达兜底 = 常数上限
        self.assertEqual(_context_token_budget(128000, 4000), 24000)  # 大窗口 → 常数上限
        self.assertEqual(_context_token_budget(8000, 1000), 7000)  # 小窗口 → 自动收紧
        self.assertEqual(_context_token_budget(1200, 4000), 1000)  # 极小窗口 → 下限保护


if __name__ == "__main__":
    unittest.main()
