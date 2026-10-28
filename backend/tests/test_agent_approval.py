"""HITL 工具审批测试（E4，二批 3.5）：整组挂起零执行 / 恢复原子补齐 / 拒绝保守 /
args_hash 漂移 fail-close（A14）/ 过期幂等巡检（A34）/ 挂起取消 / 会话阻塞。

装配方式：真注册表注入 fake_write（dangerous_write）+ 直插发布快照行（绕过一期
「首版不含写工具」发布校验——该校验属发布流纪律，E4 测试的挂起/恢复机制直接构造快照）。
"""

from __future__ import annotations

import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine, seed_chat_channel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_RUN_TERMINAL_STATUSES,
    AgentMessage,
    AgentProfile,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
    AgentRunTrace,
    AgentSession,
    AgentToolApproval,
    AgentToolCallLog,
    AgentToolResource,
    AgentToolResourceVersion,
)
from app.modules.agent.service import approval_service
from app.modules.agent.service import tool_registry as registry_module
from app.modules.agent.service.runtime import model_wrapper as model_wrapper_module
from app.modules.agent.service.runtime import run_service as run_service_module
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import (
    RUNTIME_ALLOWED_TOOLS,
    RegisteredTool,
    bootstrap_registry,
    sync_resources,
)
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.base.model.sys import SysLog

WRITE_CALLS: list[str] = []


class _FakeWriteArgs(BaseModel):
    keyword: str


def _fake_write_func(args: _FakeWriteArgs, ctx) -> str:  # noqa: ANN001
    WRITE_CALLS.append(args.keyword)
    return f"written:{args.keyword}"


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _ScriptedChatModel:
    """首轮要求调用 fake_write；恢复轮（尾部为组结果 ToolMessage）给最终回答。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def bind_tools(self, tools, **kwargs):
        # 生产装配无条件接线（工具 schema 下发）；桩无需绑定状态，适配为透传
        return self

    def generate(self, messages, **kwargs):
        msgs = messages[0] if messages and isinstance(messages[0], list) else messages
        last = msgs[-1] if msgs else None
        if isinstance(last, ToolMessage):
            return LLMResult(
                generations=[[ChatGeneration(message=AIMessage(content="审批流程已处理完毕"))]],
                llm_output={"usage": {"totalTokens": 30}},
            )
        return LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {"name": "fake_write", "args": {"keyword": "k1"}, "id": "call_1", "type": "tool_call"}
                            ],
                        )
                    )
                ]
            ],
            llm_output={"usage": {"totalTokens": 60}},
        )


class ApprovalFlowTestCase(unittest.TestCase):
    """挂起 → 决定 → 恢复的整链路（A24 三概念分离的机制层）。"""

    def setUp(self):
        # 测试显式解冻：生产默认 APPROVAL_CHAIN_ENABLED=False（冻结，见 FrozenChainTestCase），
        # 本用例族验证的是状态机机制本身
        patcher = patch.object(approval_service, "APPROVAL_CHAIN_ENABLED", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentSession.__table__,
                AgentMessage.__table__,
                AgentRunTrace.__table__,
                AgentToolApproval.__table__,
                AgentToolCallLog.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                AiProvider.__table__,
                AiModel.__table__,
                AiModelProfile.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        seed_chat_channel(self.engine)
        sync_resources(self.session)
        WRITE_CALLS.clear()
        # 注入 fake_write（dangerous_write）进注册表 + 允许列表（teardown 还原）
        self._saved_allowed = set(RUNTIME_ALLOWED_TOOLS)
        RUNTIME_ALLOWED_TOOLS.add("fake_write")
        registry_module._registry["fake_write"] = RegisteredTool(
            name="fake_write",
            description="测试写入工具",
            level="dangerous_write",
            args_model=_FakeWriteArgs,
            func=_fake_write_func,
            module="test",
        )
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.profile = AgentProfile(
            code="ag-e4test",
            name="审批测试",
            model_profile_code="deepseek-chat",
            system_prompt="测试",
            tools=json.dumps(["fake_write"]),
            status="published",
            created_by=1,
        )
        self.session.add(self.profile)
        self.session.commit()
        self.session.refresh(self.profile)
        self._publish_snapshot()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        RUNTIME_ALLOWED_TOOLS.clear()
        RUNTIME_ALLOWED_TOOLS.update(self._saved_allowed)
        bootstrap_registry()

    def _publish_snapshot(self) -> None:
        """直插发布快照 + is_current 记录（绕过一期「首版不含写工具」发布校验）。"""
        params = {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}
        payload = {
            "profile": {
                "name": "审批测试",
                "systemPrompt": "测试",
                "maxTokens": 4000,
                "maxToolRounds": 12,
                "timeoutSeconds": 60,
                "temperature": 0.5,
                "enableMemory": True,
            },
            "modelProfileCode": "deepseek-chat",
            "tools": ["fake_write"],
            "toolResourceSnapshots": [
                {"toolName": "fake_write", "displayName": "写入", "level": "dangerous_write", "parameters": params}
            ],
            "guardrailsVersion": "1",
        }
        snapshot = AgentProfileSnapshot(
            profile_id=self.profile.id,
            version=1,
            source_draft_version=1,
            snapshot_hash="test-hash",
            agent_name="审批测试",
            agent_code=self.profile.code,
            snapshot_json=json.dumps(payload, ensure_ascii=False),
            created_by=1,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        self.session.add(
            AgentProfilePublishRecord(
                profile_id=self.profile.id,
                snapshot_id=snapshot.id,
                action="publish",
                is_current=1,
                operated_by=1,
            )
        )
        self.session.commit()

    def _invoke(self, user=None, session_id: int | None = None, model=None) -> dict:
        svc = AgentRunService(self.session)
        with patch.object(model_wrapper_module, "LoomChatModel", model or _ScriptedChatModel):
            return svc.invoke_run(
                profile_id=self.profile.id,
                session_id=session_id,
                question="执行写入",
                run_mode="published",
                current_user=user or self.owner,
            )

    def _trace(self) -> AgentRunTrace:
        self.session.expire_all()
        return self.session.exec(select(AgentRunTrace).order_by(AgentRunTrace.id.desc())).first()

    def _approval(self) -> AgentToolApproval:
        self.session.expire_all()
        return self.session.exec(select(AgentToolApproval)).one()

    def _messages(self, session_id: int) -> list[AgentMessage]:
        self.session.expire_all()
        return list(
            self.session.exec(
                select(AgentMessage).where(AgentMessage.session_id == session_id).order_by(AgentMessage.id)
            ).all()
        )

    def _wait_terminal(self, timeout: float = 6.0) -> AgentRunTrace:
        deadline = time.time() + timeout
        while time.time() < deadline:
            trace = self._trace()
            if trace.status in AGENT_RUN_TERMINAL_STATUSES:
                return trace
            time.sleep(0.05)
        self.fail(f"恢复执行未在时限内到达终态（status={self._trace().status}）")

    # --- 挂起 ---

    def test_suspends_whole_round_without_executing(self):
        """整组预检：零执行 + 占位不入消息 + 审批行 pending（args_hash 锚定）+ trace waiting。"""
        result = self._invoke()
        self.assertEqual(result["status"], "waiting_approval")
        self.assertEqual(WRITE_CALLS, [])  # 整轮零执行（整组预检，二批 3.5）

        trace = self._trace()
        self.assertEqual(trace.status, "waiting_approval")  # 非终态（D30）
        self.assertIsNone(trace.duration_ms)  # duration 不含等待，终态时才落

        messages = self._messages(result["sessionId"])
        self.assertEqual([m.role for m in messages], ["user", "assistant"])  # 审批占位永不入消息
        meta = json.loads(messages[1].meta)
        self.assertEqual(meta["toolCalls"][0]["id"], "call_1")

        row = self._approval()
        self.assertEqual(row.status, "pending")
        self.assertEqual(row.tool_name, "fake_write")
        self.assertEqual(row.tool_call_id, "call_1")
        self.assertEqual(row.requested_by, 1)
        self.assertEqual(row.args_hash, approval_service.args_hash_of({"keyword": "k1"}))  # args_hash 审批锚点

    def test_session_blocked_while_pending(self):
        """pending 阻塞：挂起会话拒绝新 run（发起段 409）。"""
        result = self._invoke()
        with self.assertRaises(HTTPException) as ctx:
            self._invoke(session_id=result["sessionId"])  # 同会话第二次发起 → 阻塞
        self.assertEqual(ctx.exception.status_code, 409)

    def test_readonly_round_not_suspended(self):
        """无需审批的轮次照常执行（防误挂起冒烟）。"""
        saved_calls = registry_module._registry.pop("fake_write")
        try:
            with patch.object(model_wrapper_module, "LoomChatModel", _ScriptedChatModel):
                result = AgentRunService(self.session).invoke_run(
                    profile_id=self.profile.id,
                    session_id=None,
                    question="普通问题",
                    run_mode="published",
                    current_user=self.owner,
                )
            # 模型桩仍要求调 fake_write（未注册→拒绝回填），但不触发挂起
            self.assertEqual(result["status"], "completed")
        finally:
            registry_module._registry["fake_write"] = saved_calls

    # --- 决定与恢复 ---

    def test_requester_cannot_decide_own(self):
        """审批人权限不授予请求者（403）。"""
        result = self._invoke()
        row = self._approval()
        with self.assertRaises(HTTPException) as ctx:
            approval_service.decide(self.session, approval_id=row.id, action="approve", current_user=self.owner)
        self.assertEqual(ctx.exception.status_code, 403)
        _ = result

    def test_decide_conditional_update_idempotent(self):
        """并发双 decide：条件更新只允许一个赢家（第二个 409）。"""
        self._invoke()
        row = self._approval()
        approval_service.decide(self.session, approval_id=row.id, action="reject", current_user=self.other)
        with self.assertRaises(HTTPException) as ctx:
            approval_service.decide(self.session, approval_id=row.id, action="approve", current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_approve_resumes_group_and_completes(self):
        """批准 → 恢复：组执行（executing 租约 → succeeded）+ 恰一权威 ToolMessage + completed。"""
        result = self._invoke()
        row = self._approval()
        decided = approval_service.decide(self.session, approval_id=row.id, action="approve", current_user=self.other)
        self.assertEqual(decided.status, "approved")
        # 恢复线程异步启动：模型桩 patch 必须覆盖线程生命周期（线程内 import 解析源模块属性）
        with patch.object(model_wrapper_module, "LoomChatModel", _ScriptedChatModel):
            resumed = AgentRunService(self.session).resume_trace(decided.trace_id)
            self.assertTrue(resumed["resumed"])
            trace = self._wait_terminal()

        trace = self._wait_terminal()
        self.assertEqual(trace.status, "completed")
        self.assertEqual(WRITE_CALLS, ["k1"])  # 批准后确定性执行原调用
        self.assertGreaterEqual(trace.duration_ms, 0)  # 不含审批等待的执行时长

        row2 = self._approval()
        self.assertEqual(row2.status, "succeeded")
        self.assertIsNotNone(row2.lease_expires_at)  # executing 租约已写
        self.assertIsNotNone(row2.executed_at)
        self.assertIn("written:k1", row2.result_summary or "")

        messages = self._messages(result["sessionId"])
        roles = [m.role for m in messages]
        self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])  # 原子单元补齐 + 收尾
        self.assertEqual(messages[2].tool_call_id, "call_1")  # 每 tool_call_id 恰一权威结果
        self.assertIn("written:k1", messages[2].content)
        logs = self.session.exec(select(AgentToolCallLog)).all()
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].success)

    def test_reject_blocks_whole_group_conservatively(self):
        """组内任一拒绝 → 全组不执行：approved 也收口、普通调用标记未执行（保守）。"""

        # 同轮两个调用：fake_write（需审批）+ current_time（readonly 普通调用，注册在案）
        class _TwoCallsModel(_ScriptedChatModel):
            def generate(self, messages, **kwargs):
                msgs = messages[0] if messages and isinstance(messages[0], list) else messages
                if isinstance(msgs[-1], ToolMessage):
                    return LLMResult(
                        generations=[[ChatGeneration(message=AIMessage(content="组内拒绝已知晓"))]],
                        llm_output={"usage": {"totalTokens": 10}},
                    )
                return LLMResult(
                    generations=[
                        [
                            ChatGeneration(
                                message=AIMessage(
                                    content="",
                                    tool_calls=[
                                        {
                                            "name": "fake_write",
                                            "args": {"keyword": "k1"},
                                            "id": "call_1",
                                            "type": "tool_call",
                                        },
                                        {"name": "current_time", "args": {}, "id": "call_2", "type": "tool_call"},
                                    ],
                                )
                            )
                        ]
                    ],
                    llm_output={"usage": {"totalTokens": 40}},
                )

        result = self._invoke(model=_TwoCallsModel)
        row = self._approval()
        approval_service.decide(self.session, approval_id=row.id, action="reject", current_user=self.other)
        # 恢复线程内的模型桩：patch 须覆盖线程执行期（线程内 import 解析源模块属性）
        with patch.object(model_wrapper_module, "LoomChatModel", _TwoCallsModel):
            resumed = AgentRunService(self.session).resume_trace(row.trace_id)
            self.assertTrue(resumed["resumed"])
            trace = self._wait_terminal()
        self.assertEqual(trace.status, "completed")
        self.assertEqual(WRITE_CALLS, [])  # 写操作一律不执行

        messages = self._messages(result["sessionId"])
        tool_msgs = [m for m in messages if m.role == "tool"]
        self.assertEqual(len(tool_msgs), 2)
        by_id = {m.tool_call_id: m for m in tool_msgs}
        self.assertIn("审批未通过", by_id["call_1"].content)
        self.assertIn("因审批组挂起未执行", by_id["call_2"].content)  # 普通调用保守不执行
        row2 = self._approval()
        self.assertEqual(row2.status, "rejected")

    def test_args_hash_drift_fail_close(self):
        """A14：审批锚定 args 与恢复时实际 args 不一致 → 拒绝执行 + 行 failed。"""
        self._invoke()
        row = self._approval()
        approval_service.decide(self.session, approval_id=row.id, action="approve", current_user=self.other)
        row.args_hash = "0" * 64  # 篡改审批锚点（模拟存储被改/参数漂移）
        self.session.add(row)
        self.session.commit()

        with patch.object(model_wrapper_module, "LoomChatModel", _ScriptedChatModel):
            resumed = AgentRunService(self.session).resume_trace(row.trace_id)
            self.assertTrue(resumed["resumed"])
            trace = self._wait_terminal()
        self.assertEqual(trace.status, "completed")
        self.assertEqual(WRITE_CALLS, [])  # 漂移不可利用：未执行

        self.session.expire_all()
        row2 = self.session.exec(select(AgentToolApproval)).one()
        self.assertEqual(row2.status, "failed")
        self.assertIn("args_hash", row2.result_summary or "")

    # --- 过期与取消 ---

    def test_expiry_sweep_conditional_idempotent_and_resume(self):
        """A34：过期巡检条件更新幂等（二次扫描 0 新增）+ 组终局触发恢复。"""
        self._invoke()
        row = self._approval()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        self.session.add(row)
        self.session.commit()

        first = approval_service.sweep_approvals(self.session)
        self.assertEqual(first["expired"], 1)
        self.assertIn(row.trace_id, first["resumeTraceIds"])
        second = approval_service.sweep_approvals(self.session)
        self.assertEqual(second["expired"], 0)  # 条件更新幂等：expired 不再流转

        self.session.expire_all()
        row2 = self.session.exec(select(AgentToolApproval)).one()
        self.assertEqual(row2.status, "expired")
        with patch.object(model_wrapper_module, "LoomChatModel", _ScriptedChatModel):
            resumed = AgentRunService(self.session).resume_trace(row2.trace_id)
            self.assertTrue(resumed["resumed"])
            trace = self._wait_terminal()
        self.assertEqual(trace.status, "completed")
        self.assertEqual(WRITE_CALLS, [])  # 过期 → 全组不执行

    def test_cancel_suspended_run(self):
        """挂起中取消：行 cancelled + ToolMessage 补齐配对 + trace 终态（无模型续跑）。"""
        result = self._invoke()
        trace = self._trace()
        token = (trace.error or "").split(":", 1)[1]
        stop = AgentRunService(self.session).stop_run(token, self.owner)
        self.assertTrue(stop["stopped"])

        self.session.expire_all()
        trace2 = self.session.get(AgentRunTrace, trace.id)
        self.assertEqual(trace2.status, "cancelled")
        row = self.session.exec(select(AgentToolApproval)).one()
        self.assertEqual(row.status, "cancelled")
        messages = self._messages(result["sessionId"])
        tool_msgs = [m for m in messages if m.role == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("未执行", tool_msgs[0].content)

    def test_stop_without_local_handle_writes_cancel_token(self):
        """P0-8 前置#1（异步审查）：本进程无 handle（跨 worker/已结束）时，stop 仍必须
        写入取消令牌——那是执行侧唯一的跨进程取消信号，此前该分支静默漏写且返回
        「令牌将生效于执行侧」的假话。测试环境无 Redis → 断言走内存降级路径（同语义）。"""
        token = "cross-worker-token"
        result = AgentRunService(self.session).stop_run(token, self.owner)
        self.assertFalse(result["stopped"])
        self.assertIn("取消令牌已写入", result["message"])

        from app.modules.base.service.cache_service import cache_get

        self.assertEqual(
            cache_get(f"{run_service_module.CANCEL_KEY_PREFIX}{token}"),
            "1",
        )

    def test_args_cleanup_after_retention(self):
        """终局行超保留期 → args_json 清理（仅留摘要与 hash）。"""
        self._invoke()
        row = self._approval()
        approval_service.decide(self.session, approval_id=row.id, action="reject", current_user=self.other)
        row.decided_at = datetime.now(UTC) - timedelta(days=approval_service.APPROVAL_ARGS_RETENTION_DAYS + 1)
        self.session.add(row)
        self.session.commit()

        approval_service.sweep_approvals(self.session)
        self.session.expire_all()
        row2 = self.session.exec(select(AgentToolApproval)).one()
        self.assertIsNone(row2.args_json)
        self.assertIsNotNone(row2.args_summary)  # 摘要保留
        self.assertTrue(row2.args_hash)

    def test_lease_breach_surface_for_reconcile(self):
        """A25：租约到期仍 executing → 残留清单可见（人工核对入口数据面）。"""
        self._invoke()
        row = self._approval()
        approval_service.decide(self.session, approval_id=row.id, action="approve", current_user=self.other)
        # 模拟进入 executing 后崩溃：手工置 executing + 过期租约
        row.status = "executing"
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        self.session.add(row)
        self.session.commit()

        result = approval_service.sweep_approvals(self.session)
        self.assertEqual(len(result["staleExecuting"]), 1)
        self.assertEqual(result["staleExecuting"][0]["toolName"], "fake_write")
        self.session.expire_all()
        row2 = self.session.exec(select(AgentToolApproval)).one()
        self.assertEqual(row2.status, "executing")  # 不自动改状态——人工核对收口


class FrozenChainTestCase(unittest.TestCase):
    """E4 冻结总开关默认态（复核 N-1）：APPROVAL_CHAIN_ENABLED=False 下四端行为。"""

    def setUp(self):
        self.engine = make_test_engine(tables=[AgentToolApproval.__table__])
        self.session = Session(self.engine)
        bootstrap_registry()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _seed_pending_row(self) -> None:
        self.session.add(
            AgentToolApproval(
                session_id=1,
                trace_id=1,
                tool_call_group_id="g1",
                tool_round=1,
                tool_call_id="c1",
                tool_name="current_time",
                args_hash="h",
                status="pending",
                requested_by=1,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        self.session.commit()

    def test_has_pending_false_despite_pending_row(self):
        """阻塞端解除：遗留 pending 行不再让发起段 409 锁死会话（巡检停跑后无自愈路径）。"""
        self._seed_pending_row()
        self.assertFalse(approval_service.has_pending(self.session, 1))

    def test_required_false_and_sweep_noop(self):
        """产生端与巡检端短路：判定恒 False、巡检空转返回全零。"""
        self.assertFalse(approval_service.approval_required_for("current_time"))
        self.assertEqual(
            approval_service.sweep_approvals(self.session),
            {"expired": 0, "staleExecuting": [], "argsCleaned": 0, "resumeTraceIds": []},
        )
        # 冻结短路不误伤存量行：pending 行原样保留（解冻后语义不变）
        self._seed_pending_row()
        row = self.session.exec(select(AgentToolApproval)).one()
        self.assertEqual(row.status, "pending")

    def test_create_group_fail_fast(self):
        """防御性 fail-fast：绕过 approval_required_for 直调时显式拒绝，不静默零行挂起。"""
        with self.assertRaises(HTTPException) as ctx:
            approval_service.create_group(
                self.session,
                trace_id=1,
                session_id=1,
                tool_round=1,
                ai_message=AIMessage(content=""),
                snapshot_id=None,
                requested_by=1,
            )
        self.assertEqual(ctx.exception.status_code, 409)
