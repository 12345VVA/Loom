"""agent 全流程 live e2e（正式测试层之二）：真实渠道驱动 发布 → 对话 → 工具执行 → 审计。

DEEPSEEK_API_KEY 缺失自动 skipTest（CI 零外呼；本地配置 key 后自动启用——形态对齐
test_ai_deepseek_live）。与 mock 集成层（test_agent_e2e_full.py）的分工：本套件验证
真 tokenizer、真工具 schema 下发（bind_tools）、真六关发布、真模型 tool_calls 决策的
端到端通断——mock 层替代不了这一条。
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from dotenv import dotenv_values
from helpers import make_test_engine
from sqlmodel import Session, select

from app.core.secret import encrypt_secret
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
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.ai.model.ai import (
    AiGovernanceRule,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiProvider,
    AiRuntimeInvocation,
)
from app.modules.base.model.sys import SysLog


def _api_key() -> str:
    value = os.environ.get("DEEPSEEK_API_KEY")
    if value:
        return value.strip()
    env_path = Path(__file__).resolve().parents[1] / ".env"
    return str(dotenv_values(env_path).get("DEEPSEEK_API_KEY") or "").strip()


class AgentLiveE2ETestCase(unittest.TestCase):
    """真渠道全流程：发布（真六关）→ invoke（真 LLM + 真工具）→ 审计断言。"""

    def setUp(self):
        key = _api_key()
        if not key:
            self.skipTest("未配置 DEEPSEEK_API_KEY，live e2e 跳过（CI 零外呼）")
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
                AiModelCallLog.__table__,
                AiGovernanceRule.__table__,
                AiRuntimeInvocation.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        # 真渠道数据（E15 窗口校验需要 context_window；24000 预算 + 4000 输出 ≤ 64000）
        with Session(self.engine) as s:
            provider = AiProvider(
                code="deepseek",
                name="DeepSeek Live",
                adapter="deepseek",
                base_url="https://api.deepseek.com",
                api_key_cipher=encrypt_secret(key),
                is_active=True,
            )
            s.add(provider)
            s.flush()
            model = AiModel(
                provider_id=provider.id,
                code="deepseek-chat",
                name="deepseek-chat",
                context_window=64000,
                is_active=True,
            )
            s.add(model)
            s.flush()
            s.add(AiModelProfile(code="deepseek-chat", name="deepseek-chat", model_id=model.id))
            s.commit()
        sync_resources(self.session)
        self.service = AgentProfileService(self.session)

        class _Owner:
            id = 1
            name = "live-tester"
            is_super_admin = True

        self.owner = _Owner()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_live_publish_and_tool_call_flow(self):
        """真发布（六关）→ invoke 问时间 → 真模型 tool_calls → 工具真执行 → 审计断言。"""
        profile = self.service.add(
            {
                "name": "live-e2e",
                "system_prompt": "你是测试智能体，回答简洁。",
                "model_profile_code": "deepseek-chat",
                "tools": ["current_time"],
                "max_tokens": 2000,
                "max_tool_rounds": 4,
                "timeout_seconds": 120,
                "temperature": 0.1,
                "enable_memory": False,
                "execution_mode": "chat",
            },
            self.owner,
        )
        snapshot = self.service.publish(profile.id, self.owner)
        self.assertEqual(snapshot.version, 1)

        svc = AgentRunService(self.session)
        result = svc.invoke_run(
            profile_id=profile.id,
            session_id=None,
            question="请使用工具查询当前的准确时间，然后告诉我。",
            run_mode="published",
            current_user=self.owner,
        )
        self.assertEqual(result["status"], "completed", f"live run 未完成：{result}")

        self.session.expire_all()  # worker 线程独立连接提交——强制重读
        trace = self.session.exec(select(AgentRunTrace).order_by(AgentRunTrace.id.desc())).first()
        print(
            f"[debug] model_calls={trace.model_calls} prompt={trace.prompt_tokens} completion={trace.completion_tokens}"
        )
        for lg in self.session.exec(select(AgentToolCallLog)).all():
            print(f"[debug] log {lg.tool_name} success={lg.success} dur={lg.duration_ms} reason={lg.skipped_reason}")
        self.assertEqual(trace.model_calls, 2)  # 工具轮 + 回答轮
        self.assertEqual(trace.tool_rounds, 1)
        self.assertGreater(trace.prompt_tokens, 0)

        log = self.session.exec(select(AgentToolCallLog)).one()
        self.assertEqual(log.tool_name, "current_time")
        self.assertTrue(log.success, f"工具执行失败：{log.error}")
        self.assertIsNone(log.skipped_reason)
        self.assertIsNotNone(log.duration_ms)  # 本地工具微秒级执行——0ms 亦是如实记录

        msgs = self.session.exec(select(AgentMessage).order_by(AgentMessage.id)).all()
        tool_msg = next(m for m in msgs if m.role == "tool")
        self.assertTrue(tool_msg.content)
        assistant_final = [m for m in msgs if m.role == "assistant" and m.content]
        self.assertTrue(assistant_final, "无非空最终回复")


if __name__ == "__main__":
    unittest.main()
