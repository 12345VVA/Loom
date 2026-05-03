from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch
import json

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.secret import decrypt_secret, encrypt_secret, mask_secret
import httpx
from app.framework.controller_meta import CrudQuery, _invoke_service
from app.modules.ai.model.ai import (
    AI_ADAPTERS,
    AiChatRequest,
    AiCatalogImportRequest,
    AiImageRequest,
    AiGenerationTask,
    AiModel,
    AiModelCallLog,
    AiModelCallLogRead,
    AiModelCreateRequest,
    AiModelProfile,
    AiModelProfileCreateRequest,
    AiProvider,
    AiProviderCreateRequest,
    AiProviderRead,
    AiProviderUpdateRequest,
    AiResponseFormatRequest,
    AiTaskSubmitRequest,
)
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.factory import ADAPTERS, BailianAdapter, DeepSeekAdapter, VolcengineArkAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.ai_service import AiGenerationTaskService, AiModelCallLogService, AiModelProfileService, AiModelRegistryService, AiModelRuntimeService, AiModelService, AiProviderService
from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task


def _parse_sse_chunks(chunks: list[str]) -> list[dict]:
    events = []
    for part in "".join(chunks).split("\n\n"):
        part = part.strip()
        if not part.startswith("data:"):
            continue
        events.append(json.loads(part[5:].strip()))
    return events


class AiModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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

    def test_provider_update_saves_new_secret_when_previous_secret_is_empty(self):
        service = AiProviderService(self.session)
        provider_response = service.add(
            AiProviderCreateRequest(
                code="volcengine-ark",
                name="火山方舟",
                adapter="volcengine-ark",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
            )
        )

        service.update(
            AiProviderUpdateRequest(
                id=provider_response["id"],
                code="volcengine-ark",
                name="火山方舟",
                adapter="volcengine-ark",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key="volc-secret-key",
            )
        )

        saved = self.session.get(AiProvider, provider_response["id"])
        self.assertEqual(decrypt_secret(saved.api_key_cipher), "volc-secret-key")
        self.assertEqual(saved.api_key_mask, "volc****-key")
        self.assertTrue(service.info(saved.id)["hasApiKey"])

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

    def test_provider_page_accepts_framework_injected_query(self):
        service = AiProviderService(self.session)
        service.add(
            AiProviderCreateRequest(
                code="openai",
                name="OpenAI",
                adapter="openai-compatible",
                base_url="https://api.openai.com/v1",
            )
        )

        result = _invoke_service(service.page, query=CrudQuery(page=1, size=10), current_user=None)

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0]["code"], "openai")
        self.assertIn("hasApiKey", result.items[0])

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

    def test_runtime_logs_upstream_request_id(self):
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
                return {"content": "ok", "raw": {"id": "1"}, "usage": {"totalTokens": 3}, "requestId": "upstream-1"}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.request_id, "upstream-1")

    def test_runtime_stream_chat_outputs_events_and_logs_success(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", default_config='{"temperature":0.3}', is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, max_tokens=64, is_active=True)
        self.session.add(profile)
        self.session.commit()
        seen_options = {}

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                seen_options.update(options)
                yield {"event": "delta", "content": "he"}
                yield {"event": "delta", "content": "llo"}
                yield {"event": "done", "usage": {"promptTokens": 1, "completionTokens": 2, "totalTokens": 3}, "requestId": "stream-1"}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            chunks = list(AiModelRuntimeService(self.session).stream_chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}], options={"temperature": 0.5})))

        events = _parse_sse_chunks(chunks)
        self.assertEqual([item["event"] for item in events], ["start", "delta", "delta", "done"])
        self.assertEqual(events[-1]["content"], "hello")
        self.assertEqual(seen_options["temperature"], 0.5)
        self.assertEqual(seen_options["max_tokens"], 64)
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.request_id, "stream-1")
        self.assertEqual(log.total_tokens, 3)

    def test_runtime_stream_chat_structured_done_parse_error_does_not_fail(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="default-chat", name="Default", model_id=model.id, scenario="default", response_format='{"type":"json_object"}', is_default=True, is_active=True)
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "not json"}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            events = _parse_sse_chunks(list(AiModelRuntimeService(self.session).stream_chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))))

        self.assertEqual(events[-1]["event"], "done")
        self.assertIsNone(events[-1]["parsed"])
        self.assertTrue(events[-1]["parseError"])

    def test_runtime_stream_chat_unsupported_outputs_error_and_logs(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
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
            def stream_chat(self, *, model, messages, options):
                raise UnsupportedCapabilityError("no stream")

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            events = _parse_sse_chunks(list(AiModelRuntimeService(self.session).stream_chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))))

        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(events[-1]["status"], 501)
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "unsupported")

    def test_runtime_stream_chat_fallback_only_before_first_delta(self):
        primary_provider = AiProvider(code="primary", name="Primary", adapter="openai-compatible", is_active=True)
        fallback_provider = AiProvider(code="fallback", name="Fallback", adapter="openai-compatible", is_active=True)
        self.session.add(primary_provider)
        self.session.add(fallback_provider)
        self.session.commit()
        self.session.refresh(primary_provider)
        self.session.refresh(fallback_provider)
        primary_model = AiModel(provider_id=primary_provider.id, code="primary-model", name="Primary", model_type="chat", is_active=True)
        fallback_model = AiModel(provider_id=fallback_provider.id, code="fallback-model", name="Fallback", model_type="chat", is_active=True)
        self.session.add(primary_model)
        self.session.add(fallback_model)
        self.session.commit()
        self.session.refresh(primary_model)
        self.session.refresh(fallback_model)
        fallback_profile = AiModelProfile(code="fallback-profile", name="Fallback", model_id=fallback_model.id, scenario="default", is_active=True)
        self.session.add(fallback_profile)
        self.session.commit()
        self.session.refresh(fallback_profile)
        primary_profile = AiModelProfile(code="primary-profile", name="Primary", model_id=primary_model.id, scenario="default", fallback_profile_id=fallback_profile.id, is_default=True, is_active=True)
        self.session.add(primary_profile)
        self.session.commit()

        class FakeAdapter:
            def __init__(self, provider):
                self.provider = provider

            def stream_chat(self, *, model, messages, options):
                if self.provider.code == "primary":
                    raise RuntimeError("primary failed")
                yield {"event": "delta", "content": "fallback ok"}

        with patch("app.modules.ai.service.ai_service.build_adapter", side_effect=lambda provider: FakeAdapter(provider)):
            events = _parse_sse_chunks(list(AiModelRuntimeService(self.session).stream_chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))))

        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["content"], "fallback ok")
        self.assertEqual(events[1]["provider"], "fallback")
        logs = self.session.exec(select(AiModelCallLog).order_by(AiModelCallLog.created_at)).all()
        self.assertEqual([item.status for item in logs], ["error", "success"])

        class LateFailAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "partial"}
                raise RuntimeError("late failed")

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=LateFailAdapter()):
            late_events = _parse_sse_chunks(list(AiModelRuntimeService(self.session).stream_chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))))

        self.assertEqual(late_events[-1]["event"], "error")
        self.assertIn("late failed", late_events[-1]["message"])

    def test_call_log_read_service_decorates_related_names_and_aliases_request_id(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="default-chat", name="Default Chat", model_id=model.id, scenario="default", is_active=True)
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        log = AiModelCallLog(
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            scenario="default",
            model_type="chat",
            status="success",
            latency_ms=12,
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            request_id="req-1",
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)

        service = AiModelCallLogService(self.session)
        page = service.page(CrudQuery(page=1, size=10))
        info = service.info(log.id)
        dto = AiModelCallLogRead(
            id=log.id,
            provider_id=provider.id,
            provider_name=provider.name,
            model_id=model.id,
            model_name=model.name,
            profile_id=profile.id,
            profile_name=profile.name,
            scenario=log.scenario,
            model_type=log.model_type,
            status=log.status,
            latency_ms=log.latency_ms,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            total_tokens=log.total_tokens,
            error_message=log.error_message,
            request_id=log.request_id,
            created_at=log.created_at,
            updated_at=log.updated_at,
        ).model_dump(by_alias=True)

        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0]["providerName"], "OpenAI")
        self.assertEqual(page.items[0]["modelName"], "GPT Test")
        self.assertEqual(page.items[0]["profileName"], "Default Chat")
        self.assertEqual(info["requestId"], "req-1")
        self.assertIn("requestId", dto)

    def test_profile_list_filters_by_related_model_type(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        chat_model = AiModel(provider_id=provider.id, code="chat-model", name="Chat Model", model_type="chat", is_active=True)
        image_model = AiModel(provider_id=provider.id, code="image-model", name="Image Model", model_type="image", is_active=True)
        self.session.add(chat_model)
        self.session.add(image_model)
        self.session.commit()
        self.session.refresh(chat_model)
        self.session.refresh(image_model)
        self.session.add(AiModelProfile(code="chat-profile", name="Chat", model_id=chat_model.id, scenario="default", is_active=True))
        self.session.add(AiModelProfile(code="image-profile", name="Image", model_id=image_model.id, scenario="default", is_active=True))
        self.session.commit()

        result = AiModelProfileService(self.session).list(
            CrudQuery(raw_params={"modelType": "image"}, eq_filters={"is_active": True})
        )

        self.assertEqual([item["code"] for item in result], ["image-profile"])
        self.assertEqual(result[0]["modelType"], "image")

    def test_model_page_does_not_use_profile_model_type_filter(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        self.session.add(AiModel(provider_id=provider.id, code="image-model", name="Image Model", model_type="image", is_active=True))
        self.session.commit()

        result = AiModelService(self.session).page(CrudQuery(page=1, size=10, raw_params={"modelType": "image"}))

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0]["code"], "image-model")

    def test_runtime_fallback_merges_fallback_options_and_preserves_request_options(self):
        primary_provider = AiProvider(code="primary", name="Primary", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-primary"), is_active=True)
        fallback_provider = AiProvider(code="fallback", name="Fallback", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-fallback"), is_active=True)
        self.session.add(primary_provider)
        self.session.add(fallback_provider)
        self.session.commit()
        self.session.refresh(primary_provider)
        self.session.refresh(fallback_provider)
        primary_model = AiModel(
            provider_id=primary_provider.id,
            code="primary-model",
            name="Primary",
            model_type="chat",
            default_config='{"temperature": 0.1, "max_tokens": 100}',
            is_active=True,
        )
        fallback_model = AiModel(
            provider_id=fallback_provider.id,
            code="fallback-model",
            name="Fallback",
            model_type="chat",
            default_config='{"temperature": 0.7, "max_tokens": 200}',
            is_active=True,
        )
        self.session.add(primary_model)
        self.session.add(fallback_model)
        self.session.commit()
        self.session.refresh(primary_model)
        self.session.refresh(fallback_model)
        fallback_profile = AiModelProfile(
            code="fallback-profile",
            name="Fallback",
            model_id=fallback_model.id,
            scenario="default",
            top_p=0.8,
            max_tokens=256,
            is_active=True,
        )
        self.session.add(fallback_profile)
        self.session.commit()
        self.session.refresh(fallback_profile)
        primary_profile = AiModelProfile(
            code="primary-profile",
            name="Primary",
            model_id=primary_model.id,
            scenario="default",
            fallback_profile_id=fallback_profile.id,
            is_default=True,
            is_active=True,
        )
        self.session.add(primary_profile)
        self.session.commit()
        seen_calls = []

        class FakeAdapter:
            def __init__(self, provider):
                self.provider = provider

            def chat(self, *, model, messages, options):
                seen_calls.append((self.provider.code, model, dict(options)))
                if self.provider.code == "primary":
                    raise RuntimeError("primary failed")
                return {"content": "fallback ok", "raw": {"id": "2"}, "usage": {"totalTokens": 5}, "requestId": "fallback-req"}

        with patch("app.modules.ai.service.ai_service.build_adapter", side_effect=lambda provider: FakeAdapter(provider)):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}], options={"temperature": 0.2})
            )

        self.assertEqual(result["provider"], "fallback")
        self.assertEqual(result["model"], "fallback-model")
        self.assertEqual(seen_calls[0][2]["temperature"], 0.2)
        self.assertEqual(seen_calls[1][2]["temperature"], 0.2)
        self.assertEqual(seen_calls[1][2]["max_tokens"], 256)
        self.assertEqual(seen_calls[1][2]["top_p"], 0.8)
        logs = self.session.exec(select(AiModelCallLog).order_by(AiModelCallLog.created_at)).all()
        self.assertEqual([item.status for item in logs], ["error", "success"])
        self.assertEqual(logs[-1].request_id, "fallback-req")

    def test_profile_json_object_response_format_is_passed_to_chat_options(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat",
            name="Default",
            model_id=model.id,
            scenario="default",
            response_format='{"type":"json_object"}',
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()
        seen_options = {}

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                seen_options.update(options)
                return {"content": '{"ok": true}', "raw": {"id": "1"}, "usage": {"totalTokens": 3}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(seen_options["response_format"], {"type": "json_object"})
        self.assertEqual(result["parsed"], {"ok": True})
        self.assertIsNone(result["parseError"])

    def test_profile_json_schema_response_format_is_normalized_and_passed_to_chat_options(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        service = AiModelProfileService(self.session)
        profile = service.add(
            AiModelProfileCreateRequest(
                code="schema-chat",
                name="Schema Chat",
                model_id=model.id,
                response_format='{"type":"json_schema","json_schema":{"name":"answer_schema","description":"Answer","schema":{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false},"strict":true}}',
                is_default=True,
            )
        )
        seen_options = {}

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                seen_options.update(options)
                return {"content": '{"answer": "ok"}', "raw": {"id": "1"}, "usage": {"totalTokens": 3}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(AiChatRequest(profile_code=profile.code, messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(seen_options["response_format"]["type"], "json_schema")
        self.assertEqual(seen_options["response_format"]["json_schema"]["name"], "answer_schema")
        self.assertEqual(seen_options["response_format"]["json_schema"]["schema"]["properties"]["answer"]["type"], "string")
        self.assertEqual(result["parsed"], {"answer": "ok"})

    def test_runtime_request_response_format_overrides_profile(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="schema-chat",
            name="Schema Chat",
            model_id=model.id,
            response_format='{"type":"json_schema","json_schema":{"name":"old_schema","schema":{"type":"object"}}}',
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()
        seen_options = {}

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                seen_options.update(options)
                return {"content": '{"ok": true}', "raw": {"id": "1"}, "usage": {"totalTokens": 3}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(
                AiChatRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    response_format=AiResponseFormatRequest(type="json_object"),
                )
            )

        self.assertEqual(seen_options["response_format"], {"type": "json_object"})

    def test_runtime_structured_output_parse_error_does_not_fail_call(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat",
            name="Default",
            model_id=model.id,
            scenario="default",
            response_format='{"type":"json_object"}',
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "not json", "raw": {"id": "1"}, "usage": {"totalTokens": 3}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertTrue(result["success"])
        self.assertIsNone(result["parsed"])
        self.assertTrue(result["parseError"])

    def test_json_schema_response_format_validation_rejects_invalid_schema(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        service = AiModelProfileService(self.session)

        invalid_payloads = [
            '{"type":"json_schema","json_schema":{"name":"bad name","schema":{"type":"object"}}}',
            '{"type":"json_schema","json_schema":{"name":"missing_schema"}}',
            '{"type":"json_schema","json_schema":{"name":"bad_schema","schema":[]}}',
        ]
        for index, response_format in enumerate(invalid_payloads):
            with self.assertRaises(HTTPException) as ctx:
                service.add(
                    AiModelProfileCreateRequest(
                        code=f"bad-schema-{index}",
                        name="Bad Schema",
                        model_id=model.id,
                        response_format=response_format,
                    )
                )
            self.assertEqual(ctx.exception.status_code, 400)

    def test_registry_returns_clear_error_when_no_default(self):
        with self.assertRaises(HTTPException) as ctx:
            AiModelRegistryService(self.session).resolve(model_type="chat", scenario="missing")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_all_declared_adapters_have_factory_bindings(self):
        self.assertTrue(AI_ADAPTERS.issubset(set(ADAPTERS.keys())))
        self.assertIn("gemini", AI_ADAPTERS)
        self.assertIn("claude", AI_ADAPTERS)
        self.assertIn("deepseek", AI_ADAPTERS)
        self.assertIn("minimax", AI_ADAPTERS)
        self.assertIs(ADAPTERS["deepseek"], DeepSeekAdapter)

    def test_call_log_controller_exposes_read_only_crud_actions(self):
        from app.modules.ai.controller.admin.log import AiModelCallLogController

        actions = tuple(item if isinstance(item, str) else item.name for item in AiModelCallLogController.meta.actions)

        self.assertEqual(actions, ("page", "info", "list"))
        self.assertNotIn("add", actions)
        self.assertNotIn("update", actions)
        self.assertNotIn("delete", actions)

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

    def test_deepseek_catalog_import_is_idempotent(self):
        service = AiProviderService(self.session)

        first = service.import_catalog(AiCatalogImportRequest(provider_code="deepseek"))
        second = service.import_catalog(AiCatalogImportRequest(provider_code="deepseek"))
        provider = self.session.exec(select(AiProvider).where(AiProvider.code == "deepseek")).first()
        models = self.session.exec(select(AiModel).where(AiModel.provider_id == provider.id)).all()

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(provider.adapter, "deepseek")
        self.assertEqual(provider.base_url, "https://api.deepseek.com")
        self.assertEqual({item.code for item in models}, {"deepseek-v4-flash", "deepseek-v4-pro"})

    def test_volcengine_catalog_import_includes_image_model(self):
        service = AiProviderService(self.session)

        result = service.import_catalog(AiCatalogImportRequest(provider_code="volcengine-ark"))
        provider = self.session.exec(select(AiProvider).where(AiProvider.code == "volcengine-ark")).first()
        models = self.session.exec(select(AiModel).where(AiModel.provider_id == provider.id)).all()
        image_model = next(item for item in models if item.code == "doubao-seedream-5.0-lite")

        self.assertTrue(result["success"])
        self.assertEqual(provider.adapter, "volcengine-ark")
        self.assertEqual(image_model.model_type, "image")
        self.assertEqual(image_model.capabilities, "image,text-to-image,image-to-image")

    def test_catalog_import_restores_soft_deleted_provider_and_models(self):
        service = AiProviderService(self.session)
        provider = AiProvider(code="deepseek", name="Deleted DeepSeek", adapter="deepseek", base_url="https://old.example.com", is_active=False, delete_time=datetime.utcnow())
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="deepseek-v4-flash",
            name="Deleted Model",
            model_type="chat",
            is_active=False,
            delete_time=datetime.utcnow(),
        )
        self.session.add(model)
        self.session.commit()

        result = service.import_catalog(AiCatalogImportRequest(provider_code="deepseek"))
        page = service.page(CrudQuery(page=1, size=10))
        restored = self.session.exec(select(AiProvider).where(AiProvider.code == "deepseek")).first()
        restored_model = self.session.exec(select(AiModel).where(AiModel.provider_id == restored.id, AiModel.code == "deepseek-v4-flash")).first()

        self.assertTrue(result["success"])
        self.assertIsNone(restored.delete_time)
        self.assertTrue(restored.is_active)
        self.assertIsNone(restored_model.delete_time)
        self.assertTrue(restored_model.is_active)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0]["code"], "deepseek")

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

    def test_openai_http_adapter_stream_chat_parses_sse_delta(self):
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        class FakeStreamResponse:
            headers = {"x-request-id": "req-stream"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter([
                    'data: {"choices":[{"delta":{"content":"hi"}}]}',
                    "",
                    "data: [DONE]",
                    "",
                ])

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(adapter.stream_chat(model="qwen-plus", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(events[0]["event"], "delta")
        self.assertEqual(events[0]["content"], "hi")
        self.assertEqual(events[0]["requestId"], "req-stream")

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

    def test_deepseek_adapter_test_uses_models_endpoint(self):
        provider = AiProvider(code="deepseek", name="DeepSeek", adapter="deepseek", api_key_cipher=encrypt_secret("sk"))
        adapter = DeepSeekAdapter(provider)

        class FakeResponse:
            headers = {"x-ds-trace-id": "ds-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]}

        with patch("httpx.get", return_value=FakeResponse()) as mocked:
            result = adapter.test()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(mocked.call_args.kwargs["headers"]["Authorization"], "Bearer sk")
        self.assertEqual(str(mocked.call_args.args[0]), "https://api.deepseek.com/models")

    def test_deepseek_adapter_chat_parses_openai_compatible_response(self):
        provider = AiProvider(code="deepseek", name="DeepSeek", adapter="deepseek", api_key_cipher=encrypt_secret("sk"))
        adapter = DeepSeekAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "ds-req-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "deepseek ok"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                }

        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            result = adapter.chat(model="deepseek-v4-flash", messages=[{"role": "user", "content": "hi"}], options={"temperature": 0.2})

        self.assertEqual(result["content"], "deepseek ok")
        self.assertEqual(result["usage"]["totalTokens"], 7)
        self.assertEqual(result["requestId"], "ds-req-1")
        self.assertEqual(str(mocked.call_args.args[0]), "https://api.deepseek.com/chat/completions")
        self.assertEqual(mocked.call_args.kwargs["json"]["model"], "deepseek-v4-flash")

    def test_volcengine_adapter_image_defaults_url_and_passes_options(self):
        provider = AiProvider(code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk"))
        adapter = VolcengineArkAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "volc-req-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"url": "https://example.com/image.png"}], "usage": {"total_tokens": 9}}

        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            result = adapter.image(
                model="doubao-seedream-4-5-251128",
                prompt="draw",
                options={"size": "2K", "watermark": True, "guidance_scale": 2.5},
            )

        self.assertEqual(str(mocked.call_args.args[0]), "https://ark.cn-beijing.volces.com/api/v3/images/generations")
        self.assertEqual(mocked.call_args.kwargs["json"]["model"], "doubao-seedream-4-5-251128")
        self.assertEqual(mocked.call_args.kwargs["json"]["prompt"], "draw")
        self.assertEqual(mocked.call_args.kwargs["json"]["response_format"], "url")
        self.assertEqual(mocked.call_args.kwargs["json"]["sequential_image_generation"], "disabled")
        self.assertEqual(mocked.call_args.kwargs["json"]["size"], "2048x2048")
        self.assertNotIn("guidance_scale", mocked.call_args.kwargs["json"])
        self.assertTrue(mocked.call_args.kwargs["json"]["watermark"])
        self.assertEqual(result["data"][0]["url"], "https://example.com/image.png")
        self.assertEqual(result["usage"]["totalTokens"], 9)
        self.assertEqual(result["requestId"], "volc-req-1")

    def test_volcengine_adapter_image_normalizes_custom_response_shapes(self):
        provider = AiProvider(code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk"))
        adapter = VolcengineArkAdapter(provider)

        class FakeResponse:
            headers = {"x-tt-logid": "tt-log-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"result": {"images": [{"image_url": "https://example.com/custom.png"}, {"base64": "abc"}]}}

        with patch("httpx.post", return_value=FakeResponse()):
            result = adapter.image(model="doubao-seedream-5.0-lite", prompt="draw", options={"response_format": "b64_json"})

        self.assertEqual(result["data"][0]["url"], "https://example.com/custom.png")
        self.assertEqual(result["data"][1]["b64_json"], "abc")
        self.assertEqual(result["requestId"], "tt-log-1")

    def test_volcengine_adapter_image_exposes_upstream_error_body(self):
        provider = AiProvider(code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk"))
        adapter = VolcengineArkAdapter(provider)

        request = httpx.Request("POST", "https://ark.cn-beijing.volces.com/api/v3/images/generations")

        class FakeResponse:
            status_code = 400
            reason_phrase = "Bad Request"
            headers = {"x-tt-logid": "tt-log-400"}
            text = '{"error":{"message":"invalid sequential_image_generation"}}'

            def raise_for_status(self):
                raise httpx.HTTPStatusError("bad request", request=request, response=self)

            def json(self):
                return {"error": {"message": "invalid sequential_image_generation"}}

        with patch("httpx.post", return_value=FakeResponse()):
            with self.assertRaises(Exception) as ctx:
                adapter.image(model="doubao-seedream-4-5-251128", prompt="draw", options={})

        self.assertIn("invalid sequential_image_generation", str(ctx.exception))
        self.assertIn("tt-log-400", str(ctx.exception))

    def test_volcengine_adapter_rejects_too_small_seedream_4_image_size(self):
        provider = AiProvider(code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk"))
        adapter = VolcengineArkAdapter(provider)

        with self.assertRaises(HTTPException) as ctx:
            adapter.image(model="doubao-seedream-4-5-251128", prompt="draw", options={"size": "1536x1536"})

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("3686400", ctx.exception.detail)

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

    def test_claude_adapter_stream_chat_parses_text_and_thinking_delta(self):
        provider = AiProvider(code="claude", name="Claude", adapter="claude", api_key_cipher=encrypt_secret("key"))
        adapter = ClaudeAdapter(provider)

        class FakeStreamResponse:
            headers = {"request-id": "c-stream"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter([
                    "event: content_block_delta",
                    'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"think"}}',
                    "",
                    "event: content_block_delta",
                    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}',
                    "",
                    "event: message_stop",
                    'data: {"type":"message_stop"}',
                    "",
                ])

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(adapter.stream_chat(model="claude-test", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(events[0]["event"], "thinking_delta")
        self.assertEqual(events[1]["event"], "delta")
        self.assertEqual(events[1]["content"], "hello")

    def test_gemini_adapter_stream_chat_parses_sse_delta(self):
        provider = AiProvider(code="gemini", name="Gemini", adapter="gemini", api_key_cipher=encrypt_secret("key"))
        adapter = GeminiAdapter(provider)

        class FakeStreamResponse:
            headers = {"x-request-id": "g-stream"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter([
                    'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}],"usageMetadata":{"totalTokenCount":3}}',
                    "",
                ])

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(adapter.stream_chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(events[0]["event"], "delta")
        self.assertEqual(events[0]["content"], "hello")

    def test_ollama_adapter_stream_chat_parses_ndjson_delta(self):
        provider = AiProvider(code="ollama", name="Ollama", adapter="ollama")
        adapter = OllamaAdapter(provider)

        class FakeStreamResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter([
                    json.dumps({"message": {"content": "hi"}, "done": False}),
                    json.dumps({"done": True, "prompt_eval_count": 1, "eval_count": 2}),
                ])

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(adapter.stream_chat(model="llama", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(events[0]["event"], "delta")
        self.assertEqual(events[0]["content"], "hi")
        self.assertEqual(events[-1]["usage"]["totalTokens"], 3)

    def test_claude_adapter_unsupported_embedding(self):
        provider = AiProvider(code="claude", name="Claude", adapter="claude", api_key_cipher=encrypt_secret("key"))
        adapter = ClaudeAdapter(provider)

        with self.assertRaises(UnsupportedCapabilityError):
            adapter.embedding(model="claude", input="hello", options={})

    def test_claude_adapter_chat_does_not_mutate_options(self):
        provider = AiProvider(code="claude", name="Claude", adapter="claude", api_key_cipher=encrypt_secret("key"))
        adapter = ClaudeAdapter(provider)
        options = {"max_tokens": 64, "temperature": 0.2}

        class FakeResponse:
            headers = {"request-id": "c-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 2}}

        with patch.object(adapter, "_post", return_value=(FakeResponse().json(), FakeResponse())):
            result = adapter.chat(model="claude-test", messages=[{"role": "user", "content": "hi"}], options=options)

        self.assertEqual(result["content"], "ok")
        self.assertEqual(options, {"max_tokens": 64, "temperature": 0.2})

    def test_json_config_validation_rejects_invalid_provider_extra_config(self):
        with self.assertRaises(HTTPException) as ctx:
            AiProviderService(self.session).add(
                AiProviderCreateRequest(
                    code="bad",
                    name="Bad",
                    adapter="openai-compatible",
                    extra_config="{bad-json",
                )
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("extraConfig", str(ctx.exception.detail))

    def test_json_config_validation_rejects_invalid_model_default_config(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)

        with self.assertRaises(HTTPException) as ctx:
            AiModelService(self.session).add(
                AiModelCreateRequest(
                    provider_id=provider.id,
                    code="bad-model",
                    name="Bad Model",
                    model_type="chat",
                    default_config="[1, 2]",
                )
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("defaultConfig", str(ctx.exception.detail))

    def test_json_config_validation_rejects_invalid_profile_configs(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)

        with self.assertRaises(HTTPException) as response_ctx:
            AiModelProfileService(self.session).add(
                AiModelProfileCreateRequest(
                    code="bad-response",
                    name="Bad Response",
                    model_id=model.id,
                    response_format="{bad-json",
                )
            )
        with self.assertRaises(HTTPException) as tools_ctx:
            AiModelProfileService(self.session).add(
                AiModelProfileCreateRequest(
                    code="bad-tools",
                    name="Bad Tools",
                    model_id=model.id,
                    tools_config="{bad-json",
                )
            )

        self.assertEqual(response_ctx.exception.status_code, 400)
        self.assertEqual(tools_ctx.exception.status_code, 400)
        self.assertIn("responseFormat", str(response_ctx.exception.detail))
        self.assertIn("toolsConfig", str(tools_ctx.exception.detail))

    def test_runtime_unsupported_capability_returns_501(self):
        provider = AiProvider(code="ollama", name="Ollama", adapter="ollama", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="image-test", name="Image Test", model_type="image", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="image-default", name="Image Default", model_id=model.id, scenario="default", is_default=True, is_active=True)
        self.session.add(profile)
        self.session.commit()

        with self.assertRaises(HTTPException) as ctx:
            AiModelRuntimeService(self.session).image(AiImageRequest(prompt="draw"))

        self.assertEqual(ctx.exception.status_code, 501)

    def test_runtime_profile_timeout_applies_to_adapter(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk-test"), is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(code="default-chat", name="Default", model_id=model.id, scenario="default", timeout=7, is_default=True, is_active=True)
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            timeout = 60

            def chat(self, *, model, messages, options):
                return {"content": "ok", "raw": {"timeout": self.timeout}, "usage": {}}

        adapter = FakeAdapter()
        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=adapter):
            result = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(result["raw"]["timeout"], 7.0)
        self.assertEqual(adapter.timeout, 60)

    def test_ai_generation_task_submit_and_execute_success(self):
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

        class FakeAsyncResult:
            id = "celery-1"

        with patch("app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.delay", return_value=FakeAsyncResult()):
            submitted = AiGenerationTaskService(self.session).submit(
                AiTaskSubmitRequest(
                    task_type="chat",
                    payload={"messages": [{"role": "user", "content": "hi"}]},
                )
            )

        task = self.session.get(AiGenerationTask, submitted["taskId"])
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.celery_task_id, "celery-1")

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "raw": {}, "usage": {"totalTokens": 1}}

        with patch("app.modules.ai.service.ai_service.build_adapter", return_value=FakeAdapter()), patch("app.modules.ai.tasks.generation_tasks.engine", self.engine):
            result = execute_ai_generation_task.run(task.id)

        self.assertTrue(result["success"])
        saved = self.session.get(AiGenerationTask, task.id)
        self.session.refresh(saved)
        self.assertEqual(saved.status, "success")
        self.assertEqual(saved.progress, 100)
        self.assertIn("ok", saved.result_payload)

    def test_ai_generation_task_submit_marks_failed_when_enqueue_fails(self):
        with patch("app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.delay", side_effect=RuntimeError("broker down")):
            with self.assertRaises(HTTPException) as ctx:
                AiGenerationTaskService(self.session).submit(AiTaskSubmitRequest(task_type="chat", payload={"messages": []}))

        self.assertEqual(ctx.exception.status_code, 503)
        task = self.session.exec(select(AiGenerationTask)).one()
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.progress, 100)
        self.assertIn("broker down", task.error_message)
        self.assertIsNone(task.celery_task_id)

    def test_ai_generation_task_does_not_overwrite_cancelled_after_runtime(self):
        task = AiGenerationTask(task_type="chat", request_payload='{"messages":[{"role":"user","content":"hi"}]}', status="pending")
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        def cancel_during_call(session: Session, running_task: AiGenerationTask, payload: dict) -> dict:
            running_task.status = "cancelled"
            running_task.finished_at = datetime.utcnow()
            session.add(running_task)
            session.commit()
            return {"content": "late result"}

        with patch("app.modules.ai.tasks.generation_tasks.engine", self.engine), patch("app.modules.ai.tasks.generation_tasks._invoke_runtime", side_effect=cancel_during_call):
            result = execute_ai_generation_task.run(task.id)

        self.assertFalse(result["success"])
        saved = self.session.get(AiGenerationTask, task.id)
        self.session.refresh(saved)
        self.assertEqual(saved.status, "cancelled")
        self.assertIsNone(saved.result_payload)

    def test_ai_generation_task_failure_cancel_and_retry(self):
        task = AiGenerationTask(task_type="chat", request_payload='{"messages":[]}', status="pending")
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        with patch("app.modules.ai.tasks.generation_tasks.engine", self.engine):
            result = execute_ai_generation_task.run(task.id)
        self.assertFalse(result["success"])
        self.session.refresh(task)
        self.assertEqual(task.status, "failed")

        class FakeAsyncResult:
            id = "retry-1"

        with patch("app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.delay", return_value=FakeAsyncResult()):
            retry = AiGenerationTaskService(self.session).retry(task.id)
        self.assertTrue(retry["success"])
        self.session.refresh(task)
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.retry_count, 1)

        cancel = AiGenerationTaskService(self.session).cancel(task.id)
        self.assertTrue(cancel["success"])
        self.session.refresh(task)
        self.assertEqual(task.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
