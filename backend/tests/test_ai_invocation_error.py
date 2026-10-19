"""AI 调用边界领域异常测试（ai↔media/notification 解耦批次3，2026-10-18）。

覆盖 AiInvocationError 的核心契约：
- 兼容性保证：HTTPException 子类（既有 handler / 防御代码零改动兼容的根基）；
- registry 三态：未配置 404 / 模型禁用 400；
- 安全拦截 400（超长输入）；
- 治理阻断 429（全链路：rule 超限 → runtime.chat）。
"""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.modules.ai.model.ai import (
    AiChatRequest,
    AiGovernanceRule,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiProvider,
)
from app.modules.ai.service.errors import AiInvocationError
from app.modules.ai.service.registry_service import AiModelRegistryService
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.ai.service.security_service import MAX_INPUT_LENGTH, AiSecurityService


class AiInvocationErrorContractTestCase(unittest.TestCase):
    def test_is_http_exception_subclass_compat(self):
        """兼容性契约：子类关系是既有 HTTPException handler/防御零改动兼容的根基"""
        err = AiInvocationError("boom", status_code=429)
        self.assertIsInstance(err, HTTPException)
        self.assertEqual(err.status_code, 429)
        self.assertEqual(err.detail, "boom")


class AiInvocationRegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _make_model_tree(self, *, provider_active: bool = True, model_active: bool = True):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=provider_active)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=model_active
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return provider, model, profile

    def test_registry_unconfigured_raises_invocation_error_404(self):
        with self.assertRaises(AiInvocationError) as ctx:
            AiModelRegistryService(self.session).resolve(model_type="chat", scenario="missing")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("未找到可用的模型调用配置", ctx.exception.detail)

    def test_registry_disabled_model_raises_invocation_error_400(self):
        self._make_model_tree(model_active=False)

        # scenario 解析在 SQL 层即过滤 is_active（落到 404），「已禁用 400」分支经
        # profile_code 直查路径可达——与生产按 code 精确调用的口径一致
        with self.assertRaises(AiInvocationError) as ctx:
            AiModelRegistryService(self.session).resolve(model_type="chat", profile_code="default-chat")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("已禁用", ctx.exception.detail)

    def test_safety_overlength_raises_invocation_error_400(self):
        with self.assertRaises(AiInvocationError) as ctx:
            AiSecurityService.check_input_safety([{"role": "user", "content": "a" * (MAX_INPUT_LENGTH + 1)}])

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("过长", ctx.exception.detail)


class AiInvocationGovernanceBlockedTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_governance_blocked_raises_invocation_error_429(self):
        # 与 test_ai_module 治理阻断用例同构：全局 day 窗口 max_requests=1，已有 1 条成功记录
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.add(
            AiGovernanceRule(
                code="global-one", name="Global One", scope_type="global", period="day", max_requests=1, is_active=True
            )
        )
        self.session.add(
            AiModelCallLog(
                provider_id=provider.id, model_id=model.id, profile_id=profile.id, model_type="chat", status="success"
            )
        )
        self.session.commit()

        with self.assertRaises(AiInvocationError) as ctx:
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
