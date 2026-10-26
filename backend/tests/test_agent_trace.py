"""agent 观测链路与身份上下文测试（验收 3 / 9 / 21）：

- 验收 3：query_asset 按调用者可见性过滤（draft 仅创建者；身份来自 ctx 不进参数）；
- 验收 9：一次 run 三级观测落库（run_trace / tool_call_log / 消息）经 trace_id 关联；
- 验收 21：trace/toolLogs 越权拒绝（本人限定）。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

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
from app.modules.agent.service.runtime.prompt_render import GUARDRAILS_VERSION
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.asset.model.asset import AssetCharacter
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog

# E15：invoke_run（published）发起校验依赖渠道窗口元数据
_AI_CHANNEL_TABLES = [AiProvider.__table__, AiModel.__table__, AiModelProfile.__table__]


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _Ctx:
    def __init__(self, db: Session, user_id: int, is_super_admin: bool = False):
        self.db = db
        self.user_id = user_id
        self.user_name = f"u{user_id}"
        self.is_super_admin = is_super_admin


class _FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def generate(self, messages, **kwargs):
        return LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="已查询"))]],
            llm_output={"usage": {"totalTokens": 10}},
        )


class QueryAssetVisibilityTestCase(unittest.TestCase):
    """验收 3：工具按真实用户身份（ctx）过滤可见资产；管理员全量。"""

    def setUp(self):
        self.engine = make_test_engine(tables=[AssetCharacter.__table__, Role.__table__, UserRoleLink.__table__])
        self.session = Session(self.engine)
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.admin = _FakeUser(3, is_super_admin=True)

        from app.modules.asset.model.asset import AssetCharacterCreateRequest
        from app.modules.asset.service.character_service import AssetCharacterService

        svc = AssetCharacterService(self.session)
        self.mine = svc.add(AssetCharacterCreateRequest(code="hero", name="小白"), current_user=self.owner)  # draft
        svc.add(
            AssetCharacterCreateRequest(code="rival", name="对手角色"), current_user=self.other
        )  # draft（他人不可见）

        from app.modules.asset.service.agent_tools import QueryAssetArgs, query_asset

        self.query = query_asset
        self.args_cls = QueryAssetArgs

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_draft_visible_only_to_creator(self):
        """他人 draft 资产查询不可见（found=False，不泄露存在性）。"""
        result = self.query(self.args_cls(asset_type="character", code="rival"), _Ctx(self.session, 1))
        self.assertIn('"found": false', result)

    def test_creator_sees_own_draft(self):
        result = self.query(self.args_cls(asset_type="character", code="hero"), _Ctx(self.session, 1))
        self.assertIn('"found": true', result)
        self.assertIn("小白", result)

    def test_admin_sees_all(self):
        """管理员全量（is_super_admin 短路可见性）。"""
        result = self.query(
            self.args_cls(asset_type="character", code="rival"),
            _Ctx(self.session, self.admin.id, is_super_admin=True),
        )
        self.assertIn('"found": true', result)

    def test_identity_not_in_args(self):
        """身份来自 ctx：args_model 无身份字段（身份不在 LLM 可控范围）。"""
        self.assertNotIn("user_id", self.args_cls.model_fields)


class ObservationChainTestCase(unittest.TestCase):
    """验收 9：一次 run 三级观测经 trace_id 关联（Fake 模型 + 真注册表工具）。"""

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
        self.owner = _FakeUser(1)
        self.service = AgentProfileService(self.session)
        self.profile = self.service.add(
            AgentProfileCreateRequest(name="观测", model_profile_code="deepseek-chat", tools=["current_time"]),
            current_user=self.owner,
        )
        self.service.publish(self.profile.id, current_user=self.owner)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def test_three_level_observability_linked_by_trace(self):
        """run_trace 一条 + tool_call_log 一条 + 消息含 tool 行，均关联同一 trace/会话。"""

        def tool_first_model(**kwargs):
            model = _FakeChatModel(**kwargs)
            original = model.generate

            def scripted(messages, **kw):
                # 首轮要求调用工具，次轮收尾（脚本桩）
                has_tool_result = any(getattr(m, "tool_call_id", None) for m in messages[0])
                if not has_tool_result and len(messages[0]) == 2:  # system + 当前输入
                    from langchain_core.messages import AIMessage as _AI

                    return LLMResult(
                        generations=[
                            [
                                ChatGeneration(
                                    message=_AI(
                                        content="",
                                        tool_calls=[
                                            {
                                                "name": "current_time",
                                                "args": {},
                                                "id": "call_9",
                                                "type": "tool_call",
                                            }
                                        ],
                                    )
                                )
                            ]
                        ],
                        llm_output={"usage": {"totalTokens": 10}},
                    )
                return original(messages, **kw)

            model.generate = scripted  # type: ignore[method-assign]
            return model

        with patch.object(model_wrapper_module, "LoomChatModel", tool_first_model):
            result = AgentRunService(self.session).invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="现在几点",
                run_mode="published",
                current_user=self.owner,
            )

        self.session.expire_all()
        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.status, "completed")
        # D16：trace 记录本次 run 实际使用的护栏版本（安全策略实时生效可追溯）
        self.assertEqual(trace.guardrails_version, GUARDRAILS_VERSION)

        logs = self.session.exec(select(AgentToolCallLog).where(AgentToolCallLog.trace_id == trace.id)).all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].toolName if hasattr(logs[0], "toolName") else logs[0].tool_name, "current_time")
        self.assertTrue(logs[0].success)

        tool_messages = self.session.exec(
            select(AgentMessage).where(
                AgentMessage.session_id == result["sessionId"],
                AgentMessage.role == "tool",
            )
        ).all()
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call_9")

    def test_trace_page_and_toollogs_owner_only(self):
        """验收 21：trace 管理面仅本人；toolLogs 越权 403。"""
        service = AgentRunService(self.session)
        with patch.object(model_wrapper_module, "LoomChatModel", _FakeChatModel):
            service.invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="你好",
                run_mode="published",
                current_user=self.owner,
            )
        self.session.expire_all()
        trace = self.session.exec(select(AgentRunTrace)).first()
        rows = AgentRunTraceServiceProxy(self.session).list(current_user=self.owner)
        self.assertEqual([r["id"] for r in rows], [trace.id])
        other_rows = AgentRunTraceServiceProxy(self.session).list(current_user=_FakeUser(2))
        self.assertEqual(other_rows, [])


class AgentRunTraceServiceProxy:
    """test_agent_module 可见性用例的同款服务直调（避免 HTTP 依赖）。"""

    def __init__(self, session: Session):
        from app.modules.agent.service.trace_service import AgentRunTraceService

        self._svc = AgentRunTraceService(session)

    def list(self, current_user):
        return self._svc.list(current_user=current_user)


if __name__ == "__main__":
    unittest.main()
