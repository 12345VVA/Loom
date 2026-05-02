from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.secret import decrypt_secret, encrypt_secret, mask_secret
from app.modules.ai.model.ai import (
    AI_ADAPTERS,
    AiChatRequest,
    AiCatalogImportRequest,
    AiModel,
    AiModelProfile,
    AiProvider,
    AiProviderCreateRequest,
    AiProviderRead,
    AiProviderUpdateRequest,
)
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.factory import ADAPTERS, BailianAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.ai_service import AiModelRegistryService, AiModelRuntimeService, AiProviderService


class AiModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_secret_encrypt_decrypt_and_mask(self):
        cipher = encrypt_secret("sk-test-secret")

        self.assertNotEqual(cipher, "sk-test-secret")
        self.assertEqual(decrypt_secret(cipher), "sk-test-secret")
        self.assertEqual(mask_secret("sk-test-secret"), "sk-t****cret")

    def test_provider_masks_secret_and_preserves_it_on_update(self):
        service = AiProviderService(self.session)
        provider_response = service.add(
            AiProviderCreateRequest(
                code="openai",
                name="OpenAI",
                adapter="openai-compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-secret-value",
            )
        )
        provider = self.session.get(AiProvider, provider_response["id"])

        self.assertNotIn("sk-secret-value", provider.api_key_cipher)
        self.assertEqual(provider.api_key_mask, "sk-s****alue")
        self.assertNotIn("apiKeyCipher", provider_response)
        self.assertTrue(provider_response["hasApiKey"])

        service.update(
            AiProviderUpdateRequest(
                id=provider.id,
                code="openai",
                name="OpenAI 2",
                adapter="openai-compatible",
                base_url="https://api.openai.com/v1",
                api_key=None,
            )
        )
        saved = self.session.get(AiProvider, provider.id)
        self.assertEqual(decrypt_secret(saved.api_key_cipher), "sk-secret-value")

        info = service.info(provider.id)
        self.assertNotIn("apiKeyCipher", info)
        self.assertTrue(info["hasApiKey"])

    def test_provider_read_dto_uses_camel_case_and_no_cipher(self):
        data = AiProviderRead(
            id=1,
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            base_url="https://api.openai.com/v1",
            api_key_mask="sk****",
            has_api_key=True,
            extra_config=None,
            is_active=True,
            sort_order=0,
            created_at="2026-05-02T00:00:00",
            updated_at="2026-05-02T00:00:00",
        ).model_dump(by_alias=True)

        self.assertIn("baseUrl", data)
        self.assertIn("apiKeyMask", data)
        self.assertIn("hasApiKey", data)
        self.assertNotIn("apiKeyCipher", data)

    def test_registry_resolves_default_profile_by_scenario_and_type(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="writer", name="Writer", model_id=model.id, scenario="content", is_default=True, is_active=True)
        self.session.add(profile)
        self.session.commit()

        resolved = AiModelRegistryService(self.session).resolve(model_type="chat", scenario="content")

        self.assertEqual(resolved["profile"].code, "writer")
        self.assertEqual(resolved["model"].code, "gpt-test")

    def test_runtime_uses_adapter_and_logs_call(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True)
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "raw": {"id": "1"}, "usage": {"promptTokens": 1, "completionTokens": 2, "totalTokens": 3}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "ok")

    def test_registry_returns_clear_error_when_no_default(self):
        with self.assertRaises(HTTPException) as ctx:
            AiModelRegistryService(self.session).resolve(model_type="chat", scenario="missing")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_all_declared_adapters_have_factory_bindings(self):
        self.assertTrue(AI_ADAPTERS.issubset(set(ADAPTERS.keys())))
        self.assertIn("gemini", AI_ADAPTERS)
        self.assertIn("claude", AI_ADAPTERS)
        self.assertIn("minimax", AI_ADAPTERS)

    def test_catalog_import_is_idempotent_and_preserves_secret(self):
        service = AiProviderService(self.session)
        provider_response = service.add(
            AiProviderCreateRequest(
                code="bailian",
                name="旧百炼",
                adapter="bailian",
                base_url="https://old.example.com",
                api_key="sk-bailian",
            )
        )
        provider = self.session.get(AiProvider, provider_response["id"])
        old_cipher = provider.api_key_cipher

        first = service.import_catalog(AiCatalogImportRequest(provider_code="bailian"))
        second = service.import_catalog(AiCatalogImportRequest(provider_code="bailian"))
        saved = self.session.get(AiProvider, provider.id)

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(saved.api_key_cipher, old_cipher)
        self.assertGreaterEqual(len(self.session.exec(select(AiModel)).all()), 1)

    def test_openai_http_adapter_chat_parses_usage_and_request_id(self):
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "req-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                }

        with patch("httpx.post", return_value=FakeResponse()):
            result = adapter.chat(model="qwen-plus", messages=[{"role": "user", "content": "hi"}], options={})

        self.assertEqual(result["content"], "ok")
        self.assertEqual(result["usage"]["totalTokens"], 3)
        self.assertEqual(result["requestId"], "req-1")

    def test_openai_http_adapter_test_raises_for_http_failure(self):
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        class FakeResponse:
            def raise_for_status(self):
                raise RuntimeError("401")

            def json(self):
                return {}

        with patch("httpx.get", return_value=FakeResponse()):
            with self.assertRaises(RuntimeError):
                adapter.test()

    def test_openai_http_adapter_test_can_explicitly_skip_model_list(self):
        provider = AiProvider(
            code="bailian",
            name="百炼",
            adapter="bailian",
            api_key_cipher=encrypt_secret("sk"),
            extra_config='{"skip_model_list_check": true}',
        )
        adapter = BailianAdapter(provider)

        class FakeResponse:
            def raise_for_status(self):
                raise RuntimeError("404")

            def json(self):
                return {}

        with patch("httpx.get", return_value=FakeResponse()):
            result = adapter.test()

        self.assertTrue(result["success"])

    def test_gemini_adapter_chat_transforms_response(self):
        provider = AiProvider(code="gemini", name="Gemini", adapter="gemini", api_key_cipher=encrypt_secret("key"))
        adapter = GeminiAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "g-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3},
                }

        with patch("httpx.post", return_value=FakeResponse()):
            result = adapter.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}], options={})

        self.assertEqual(result["content"], "hello")
        self.assertEqual(result["requestId"], "g-1")

    def test_claude_adapter_unsupported_embedding(self):
        provider = AiProvider(code="claude", name="Claude", adapter="claude", api_key_cipher=encrypt_secret("key"))
        adapter = ClaudeAdapter(provider)

        with self.assertRaises(UnsupportedCapabilityError):
            adapter.embedding(model="claude", input="hello", options={})


if __name__ == "__main__":
    unittest.main()
