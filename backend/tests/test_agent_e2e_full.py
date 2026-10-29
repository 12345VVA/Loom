"""agent 全流程·全功能 mock 集成测试（正式测试层之一，CI 常跑）。

真链路：add（draft）→ publish（真六关校验）→ invoke_run（published 快照 + Fake 模型脚本
多轮）→ 终态/审计/消息三层断言。live 真渠道套件见 test_agent_live_e2e.py。

审计断言面（调用追踪专项闭环验收）：
- tool_call_log：成功行 skipped_reason=NULL + duration 如实；失败行 success=False +
  error + skipped_reason='error'；软失败 skipped_reason='soft_failure'；
- agent_message：assistant 行 meta.toolCalls 完整（A2）；tool 行 4000 字截断（A4 口径）；
- trace：model_calls/tool_rounds/token 聚合如实。
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from helpers import make_test_engine, seed_chat_channel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AgentMessage,
    AgentProfile,
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
from app.modules.agent.service import tool_registry as registry_module
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime import model_wrapper as model_wrapper_module
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import (
    RUNTIME_ALLOWED_TOOLS,
    RegisteredTool,
    bootstrap_registry,
    sync_resources,
)
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.base.model.sys import SysLog

# ---- Fake 模型桩（脚本驱动多轮；接口对齐 LoomChatModel 装配面）----


class _FakeChatModel:
    """脚本桩：每轮 pop 一个 AIMessage；尾部为 ToolMessage 时给最终回答。"""

    def __init__(self, script: list[AIMessage], **kwargs):
        self.script = list(script)
        self.kwargs = kwargs
        self._runtime_service = None

    def bind_tools(self, tools, **kwargs):
        return self

    # 生产装配 sync 轮已切 generate_raw（usage 断链修复）——桩委托对齐
    def generate_raw(self, messages, **kwargs):
        return self.generate(messages, **kwargs)

    def generate(self, messages, **kwargs):
        msgs = messages[0] if messages and isinstance(messages[0], list) else messages
        last = msgs[-1] if msgs else None
        if isinstance(last, ToolMessage):
            reply = AIMessage(content="全部工具已执行完毕，以上是结果汇总。")
        else:
            reply = self.script.pop(0)
        usage = {"promptTokens": 500, "completionTokens": 30, "totalTokens": 530}
        return LLMResult(
            generations=[[ChatGeneration(message=reply)]],
            llm_output={"usage": usage},
        )


class _FakeUser:
    def __init__(self, user_id: int = 1):
        self.id = user_id
        self.name = "tester"
        self.is_super_admin = True


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class AgentE2EFullTestCase(unittest.TestCase):
    """全流程·全功能（mock 模型）：发布 → 多轮工具对话 → 终态/审计/消息断言。"""

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
        self.service = AgentProfileService(self.session)
        self.owner = _FakeUser(1)

        # 注入三个测试工具（readonly——发布六关可过；sync 前注入使资源层建行）
        class _Empty(BaseModel):
            pass

        self._tools = {
            "fake_fail": lambda args, ctx: (_ for _ in ()).throw(RuntimeError("工具内部炸了")),
            "fake_soft": lambda args, ctx: json.dumps({"ok": False, "error": "业务校验未通过"}, ensure_ascii=False),
            "fake_big": lambda args, ctx: "X" * 5000,
        }
        for name, func in self._tools.items():
            RUNTIME_ALLOWED_TOOLS.add(name)
            registry_module._registry[name] = RegisteredTool(
                name=name,
                description=f"{name} 测试工具",
                level="readonly",
                args_model=_Empty,
                func=func,
                module="test",
            )
        sync_resources(self.session)  # 资源层建行（发布第 4 关需要）

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        RUNTIME_ALLOWED_TOOLS.clear()
        RUNTIME_ALLOWED_TOOLS.update(
            {
                "current_time",
                "system_info",
                "query_asset",
                "search_media",
                "rename_media",
                "tag_media",
                "create_asset_draft",
                "update_asset_draft",
                "list_workflow_definitions",
            }
        )
        bootstrap_registry()

    def _publish(self, tools: list[str]) -> int:
        profile = self.service.add(
            {
                "name": f"e2e-{tools[0]}",
                "system_prompt": "你是测试智能体",
                "model_profile_code": "deepseek-chat",
                "tools": tools,
                "max_tokens": 4000,
                "max_tool_rounds": 6,
                "timeout_seconds": 60,
                "temperature": 0.3,
                "enable_memory": False,
                "execution_mode": "chat",
            },
            self.owner,
        )
        self.service.publish(profile.id, self.owner)
        return profile.id

    def _invoke(self, profile_id: int, script: list[AIMessage], question: str = "开始测试") -> dict:
        svc = AgentRunService(self.session)
        with patch.object(model_wrapper_module, "LoomChatModel", lambda **kw: _FakeChatModel(script, **kw)):
            return svc.invoke_run(
                profile_id=profile_id,
                session_id=None,
                question=question,
                run_mode="published",
                current_user=self.owner,
            )

    # ---- 用例 ----

    def test_full_flow_happy_path(self):
        """发布 → 工具轮 + 回答轮：trace/审计/消息三层断言（含 A2 meta.toolCalls）。"""
        pid = self._publish(["current_time"])
        script = [AIMessage(content="", tool_calls=[_tool_call("current_time", {}, "call_1")])]
        result = self._invoke(pid, script)

        self.assertEqual(result["status"], "completed")
        self.session.expire_all()  # worker 线程独立连接提交——强制本 session 重读
        trace = self.session.exec(select(AgentRunTrace).order_by(AgentRunTrace.id.desc())).first()
        self.assertEqual(trace.model_calls, 2)
        self.assertEqual(trace.tool_rounds, 1)
        self.assertGreater(trace.prompt_tokens, 0)
        self.assertGreater(trace.completion_tokens, 0)

        # 审计面：成功行 skipped_reason=NULL + duration 如实
        log = self.session.exec(select(AgentToolCallLog)).one()
        self.assertEqual(log.tool_name, "current_time")
        self.assertTrue(log.success)
        self.assertIsNone(log.skipped_reason)
        self.assertIsNotNone(log.duration_ms)
        self.assertIn("{}", log.args_summary)

        # 消息面：assistant 行 meta.toolCalls（A2）+ tool 行结果
        msgs = self.session.exec(select(AgentMessage).order_by(AgentMessage.id)).all()
        assistant = next(m for m in msgs if m.role == "assistant" and m.meta)
        meta = json.loads(assistant.meta)
        self.assertEqual(meta["toolCalls"][0]["name"], "current_time")
        self.assertEqual(meta["toolCalls"][0]["id"], "call_1")
        tool_msg = next(m for m in msgs if m.role == "tool")
        self.assertTrue(tool_msg.content)
        self.assertEqual(tool_msg.tool_call_id, "call_1")

    def test_tool_failure_recorded_not_silent(self):
        """工具抛异常：审计 success=False + error + skipped_reason='error'，run 不中止。"""
        pid = self._publish(["fake_fail", "current_time"])
        script = [
            AIMessage(
                content="",
                tool_calls=[_tool_call("fake_fail", {"x": 1}, "call_f"), _tool_call("current_time", {}, "call_t")],
            )
        ]
        self._invoke(pid, script)
        self.session.expire_all()

        logs = self.session.exec(select(AgentToolCallLog).order_by(AgentToolCallLog.id)).all()
        self.assertEqual(len(logs), 2)
        by_name = {row.tool_name: row for row in logs}
        failed = by_name["fake_fail"]
        self.assertFalse(failed.success)
        self.assertEqual(failed.skipped_reason, "error")
        self.assertIn("工具内部炸了", failed.error)
        ok = by_name["current_time"]
        self.assertTrue(ok.success)
        self.assertIsNone(ok.skipped_reason)

    def test_soft_failure_contract(self):
        """{"ok": false} 软失败：success=False + skipped_reason='soft_failure'。"""
        pid = self._publish(["fake_soft"])
        script = [AIMessage(content="", tool_calls=[_tool_call("fake_soft", {}, "call_s")])]
        self._invoke(pid, script)
        self.session.expire_all()

        log = self.session.exec(select(AgentToolCallLog)).one()
        self.assertFalse(log.success)
        self.assertEqual(log.skipped_reason, "soft_failure")
        self.assertIn("业务校验未通过", log.error)

    def test_oversized_tool_result_truncated_at_4000(self):
        """>4000 字工具结果：消息层截 4000 + 截断标记（A4 口径——超限部分不留全量）。"""
        pid = self._publish(["fake_big"])
        script = [AIMessage(content="", tool_calls=[_tool_call("fake_big", {}, "call_b")])]
        self._invoke(pid, script)
        self.session.expire_all()

        msgs = self.session.exec(select(AgentMessage).order_by(AgentMessage.id)).all()
        tool_msg = next(m for m in msgs if m.role == "tool")
        self.assertLessEqual(len(tool_msg.content), 4100)
        self.assertIn("已截断", tool_msg.content)


if __name__ == "__main__":
    unittest.main()
