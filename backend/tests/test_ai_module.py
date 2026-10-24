from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.celery_app import AI_TASK_QUEUES, celery_app
from app.core.secret import decrypt_secret, encrypt_secret, mask_secret
from app.framework.controller_meta import CrudQuery, _invoke_service
from app.modules.ai.model.ai import (
    AI_ADAPTERS,
    AI_MODEL_TYPES,
    AiCatalogImportRequest,
    AiChatRequest,
    AiGenerationTask,
    AiGovernanceEvent,
    AiGovernanceRule,
    AiImageRequest,
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
    AiRuntimeInvocation,
    AiTaskSubmitRequest,
)
from app.modules.ai.service.adapters.base import AdapterInputError, UnsupportedCapabilityError
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.factory import (
    ADAPTERS,
    BailianAdapter,
    DeepSeekAdapter,
    QianfanAdapter,
    VolcengineArkAdapter,
    _adapt_deepseek_options,
    build_adapter,
)
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter
from app.modules.ai.service.ai_service import (
    AiGenerationTaskService,
    AiGovernanceCleanupService,
    AiModelCallLogService,
    AiModelProfileService,
    AiModelRegistryService,
    AiModelRuntimeService,
    AiModelService,
    AiProviderService,
)
from app.modules.ai.service.errors import AiInvocationError
from app.modules.ai.service.runtime_service import _STREAM_HEARTBEAT, _with_heartbeat
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
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_profile_custom_config_merges_and_overrides_model_default_config(self):
        """Profile 的 custom_config 应能覆盖模型的 default_config（例如图片模型的 size/quality 透传参数）。"""
        model = AiModel(
            provider_id=1,
            code="test-img-model",
            name="Test Image Model",
            model_type="image",
            default_config=json.dumps({"size": "1024x1024", "quality": "standard", "keep_me": "yes"}),
        )
        profile = AiModelProfile(
            code="test-img-profile",
            name="Test Image Profile",
            model_id=1,
            custom_config=json.dumps({"size": "768x1024", "new_param": 123}),
        )
        registry = AiModelRegistryService(self.session)
        options = registry._merge_options(model, profile)
        self.assertEqual(options["size"], "768x1024")
        self.assertEqual(options["quality"], "standard")
        self.assertEqual(options["keep_me"], "yes")
        self.assertEqual(options["new_param"], 123)

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
        profile = AiModelProfile(
            code="writer", name="Writer", model_id=model.id, scenario="content", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()

        resolved = AiModelRegistryService(self.session).resolve(model_type="chat", scenario="content")

        self.assertEqual(resolved["profile"].code, "writer")
        self.assertEqual(resolved["model"].code, "gpt-test")

    def test_runtime_uses_adapter_and_logs_call(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {
                    "content": "ok",
                    "raw": {"id": "1"},
                    "usage": {"promptTokens": 1, "completionTokens": 2, "totalTokens": 3},
                }

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "ok")

    def test_runtime_logs_upstream_request_id(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "raw": {"id": "1"}, "usage": {"totalTokens": 3}, "requestId": "upstream-1"}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.request_id, "upstream-1")

    def test_runtime_stream_chat_outputs_events_and_logs_success(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="gpt-test",
            name="GPT Test",
            model_type="chat",
            default_config='{"temperature":0.3}',
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat",
            name="Default",
            model_id=model.id,
            scenario="default",
            is_default=True,
            max_tokens=64,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()
        seen_options = {}

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                seen_options.update(options)
                yield {"event": "delta", "content": "he"}
                yield {"event": "delta", "content": "llo"}
                yield {
                    "event": "done",
                    "usage": {"promptTokens": 1, "completionTokens": 2, "totalTokens": 3},
                    "requestId": "stream-1",
                }

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            chunks = list(
                AiModelRuntimeService(self.session).stream_chat(
                    AiChatRequest(messages=[{"role": "user", "content": "hi"}], options={"temperature": 0.5})
                )
            )

        events = _parse_sse_chunks(chunks)
        self.assertEqual([item["event"] for item in events], ["start", "delta", "delta", "done"])
        self.assertEqual(events[-1]["content"], "hello")
        self.assertEqual(seen_options["temperature"], 0.5)
        self.assertEqual(seen_options["max_tokens"], 64)
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.request_id, "stream-1")
        self.assertEqual(log.total_tokens, 3)

    def test_runtime_stream_chat_client_close_releases_invocation(self):
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
        self.session.commit()

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "partial"}
                yield {"event": "done", "usage": {"totalTokens": 1}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            stream = AiModelRuntimeService(self.session).stream_chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )
            next(stream)
            stream.close()

        invocation = self.session.exec(select(AiRuntimeInvocation)).one()
        self.assertEqual(invocation.status, "error")
        self.assertIsNotNone(invocation.finished_at)

    def test_runtime_stream_chat_structured_done_parse_error_does_not_fail(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
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
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "not json"}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            events = _parse_sse_chunks(
                list(
                    AiModelRuntimeService(self.session).stream_chat(
                        AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                    )
                )
            )

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
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                raise UnsupportedCapabilityError("no stream")

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            events = _parse_sse_chunks(
                list(
                    AiModelRuntimeService(self.session).stream_chat(
                        AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                    )
                )
            )

        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(events[-1]["status"], 501)
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "unsupported")

    def test_runtime_stream_chat_adapter_input_error_after_delta_emits_error(self):
        """P2：流中途抛 AdapterInputError 也必须收尾——否则前端只收到半截正文，无 done 无 error。"""
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
        self.session.commit()

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "半截"}
                raise AdapterInputError("工具调用参数非法")

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            events = _parse_sse_chunks(
                list(
                    AiModelRuntimeService(self.session).stream_chat(
                        AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                    )
                )
            )

        self.assertEqual([item["event"] for item in events], ["start", "delta", "error"])
        self.assertEqual(events[-1]["status"], 400)
        self.assertTrue(events[-1]["truncated"])  # 已下发正文 → 显式标记截断
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "error")

    def test_runtime_stream_chat_fallback_only_before_first_delta(self):
        primary_provider = AiProvider(code="primary", name="Primary", adapter="openai-compatible", is_active=True)
        fallback_provider = AiProvider(code="fallback", name="Fallback", adapter="openai-compatible", is_active=True)
        self.session.add(primary_provider)
        self.session.add(fallback_provider)
        self.session.commit()
        self.session.refresh(primary_provider)
        self.session.refresh(fallback_provider)
        primary_model = AiModel(
            provider_id=primary_provider.id, code="primary-model", name="Primary", model_type="chat", is_active=True
        )
        fallback_model = AiModel(
            provider_id=fallback_provider.id, code="fallback-model", name="Fallback", model_type="chat", is_active=True
        )
        self.session.add(primary_model)
        self.session.add(fallback_model)
        self.session.commit()
        self.session.refresh(primary_model)
        self.session.refresh(fallback_model)
        fallback_profile = AiModelProfile(
            code="fallback-profile", name="Fallback", model_id=fallback_model.id, scenario="default", is_active=True
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

        class FakeAdapter:
            def __init__(self, provider):
                self.provider = provider

            def stream_chat(self, *, model, messages, options):
                if self.provider.code == "primary":
                    raise RuntimeError("primary failed")
                yield {"event": "delta", "content": "fallback ok"}

        with patch(
            "app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda provider: FakeAdapter(provider)
        ):
            events = _parse_sse_chunks(
                list(
                    AiModelRuntimeService(self.session).stream_chat(
                        AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                    )
                )
            )

        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["content"], "fallback ok")
        self.assertEqual(events[1]["provider"], "fallback")
        logs = self.session.exec(select(AiModelCallLog).order_by(AiModelCallLog.created_at)).all()
        self.assertEqual([item.status for item in logs], ["error", "success"])

        class LateFailAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "partial"}
                raise RuntimeError("late failed")

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=LateFailAdapter()):
            late_events = _parse_sse_chunks(
                list(
                    AiModelRuntimeService(self.session).stream_chat(
                        AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                    )
                )
            )

        self.assertEqual(late_events[-1]["event"], "error")
        self.assertIn("late failed", late_events[-1]["message"])

    def _seed_fallback_chain(self, *, fallback_context_window: int | None, suffix: str = ""):
        """E15 用例夹具：primary（主，32000）→ fallback-profile（回退，窗口可配）。
        suffix 供同一用例内多轮建链去重（ai_provider.code 唯一）。"""
        primary_provider = AiProvider(
            code=f"primary{suffix}", name="Primary", adapter="openai-compatible", is_active=True
        )
        fallback_provider = AiProvider(
            code=f"fallback{suffix}", name="Fallback", adapter="openai-compatible", is_active=True
        )
        self.session.add(primary_provider)
        self.session.add(fallback_provider)
        self.session.commit()
        self.session.refresh(primary_provider)
        self.session.refresh(fallback_provider)
        primary_model = AiModel(
            provider_id=primary_provider.id,
            code=f"primary-model{suffix}",
            name="Primary",
            model_type="chat",
            context_window=32000,
            is_active=True,
        )
        fallback_model = AiModel(
            provider_id=fallback_provider.id,
            code=f"fallback-model{suffix}",
            name="Fallback",
            model_type="chat",
            context_window=fallback_context_window,
            is_active=True,
        )
        self.session.add(primary_model)
        self.session.add(fallback_model)
        self.session.commit()
        self.session.refresh(primary_model)
        self.session.refresh(fallback_model)
        fallback_profile = AiModelProfile(
            code=f"fallback-profile{suffix}",
            name="Fallback",
            model_id=fallback_model.id,
            scenario="default",
            is_active=True,
        )
        self.session.add(fallback_profile)
        self.session.commit()
        self.session.refresh(fallback_profile)
        primary_profile = AiModelProfile(
            code=f"primary-profile{suffix}",
            name="Primary",
            model_id=primary_model.id,
            scenario="default",
            fallback_profile_id=fallback_profile.id,
            is_default=True,
            is_active=True,
        )
        self.session.add(primary_profile)
        self.session.commit()

    def test_stream_fallback_rejects_path_when_window_unknown_or_small(self):
        """E15（A27 运行时面）：min_context_window 声明后，回退候选窗口未知/不足 → 拒绝该
        回退路径（不静默换小窗口模型），主调用错误归一冒泡为 error 事件。"""
        for i, fb_window in enumerate((None, 4000)):  # 未知 / 不足 8000 两种形态同判
            with self.subTest(fb_window=fb_window):
                self._seed_fallback_chain(fallback_context_window=fb_window, suffix=f"-{i}")

                class FailPrimaryAdapter:
                    def __init__(self, provider):
                        self.provider = provider

                    def stream_chat(self, *, model, messages, options):
                        if self.provider.code.startswith("primary"):
                            raise RuntimeError("primary failed")
                        yield {"event": "delta", "content": "should not happen"}

                with patch(
                    "app.modules.ai.service.runtime_service.build_adapter",
                    side_effect=lambda provider: FailPrimaryAdapter(provider),
                ):
                    events = _parse_sse_chunks(
                        list(
                            AiModelRuntimeService(self.session).stream_chat(
                                AiChatRequest(messages=[{"role": "user", "content": "hi"}]),
                                min_context_window=8000,
                            )
                        )
                    )
                self.assertEqual(events[-1]["event"], "error")
                self.assertIn("primary failed", events[-1]["message"])

    def test_chat_fallback_respects_min_context_window(self):
        """E15 sync 路径：回退候选窗口不足 → 放弃降级，AiInvocationError 归一冒泡；
        未声明约束（None）时回退照常（ai 存量调用方零变化）。"""
        self._seed_fallback_chain(fallback_context_window=4000)

        class FailPrimaryOkFallbackAdapter:
            def __init__(self, provider):
                self.provider = provider

            def chat(self, *, model, messages, options):
                if self.provider.code == "primary":
                    raise RuntimeError("primary failed")
                return {"content": "fallback ok", "raw": {}, "usage": {}}

        adapter = FailPrimaryOkFallbackAdapter
        with patch("app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda p: adapter(p)):
            with self.assertRaises(AiInvocationError):
                AiModelRuntimeService(self.session).chat(
                    AiChatRequest(messages=[{"role": "user", "content": "hi"}]),
                    min_context_window=8000,
                )
            # 未声明约束：同链同故障 → 回退成功（行为零变化）
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )
        self.assertEqual(result["content"], "fallback ok")

    def test_call_log_read_service_decorates_related_names_and_aliases_request_id(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(provider_id=provider.id, code="gpt-test", name="GPT Test", model_type="chat", is_active=True)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default Chat", model_id=model.id, scenario="default", is_active=True
        )
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
        chat_model = AiModel(
            provider_id=provider.id, code="chat-model", name="Chat Model", model_type="chat", is_active=True
        )
        image_model = AiModel(
            provider_id=provider.id, code="image-model", name="Image Model", model_type="image", is_active=True
        )
        self.session.add(chat_model)
        self.session.add(image_model)
        self.session.commit()
        self.session.refresh(chat_model)
        self.session.refresh(image_model)
        self.session.add(
            AiModelProfile(code="chat-profile", name="Chat", model_id=chat_model.id, scenario="default", is_active=True)
        )
        self.session.add(
            AiModelProfile(
                code="image-profile", name="Image", model_id=image_model.id, scenario="default", is_active=True
            )
        )
        self.session.commit()

        result = AiModelProfileService(self.session).list(
            CrudQuery(raw_params={"modelType": "image"}, eq_filters={"is_active": True})
        )

        self.assertEqual([item["code"] for item in result], ["image-profile"])
        self.assertEqual(result[0]["modelType"], "image")
        self.assertEqual(result[0]["modelCode"], "image-model")
        self.assertEqual(result[0]["providerCode"], "openai")
        self.assertEqual(result[0]["providerAdapter"], "openai-compatible")

    def test_profile_list_decorates_model_capabilities(self):
        provider = AiProvider(code="bailian-custom", name="Custom Provider", adapter="bailian", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="wan2.6-t2i",
            name="Wan Image",
            model_type="image",
            capabilities="image,text-to-image",
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        self.session.add(
            AiModelProfile(code="wan-image", name="Wan Image", model_id=model.id, scenario="default", is_active=True)
        )
        self.session.commit()

        result = AiModelProfileService(self.session).list(
            CrudQuery(raw_params={"modelType": "image"}, eq_filters={"is_active": True})
        )

        self.assertEqual(result[0]["providerCode"], "bailian-custom")
        self.assertEqual(result[0]["providerAdapter"], "bailian")
        self.assertEqual(result[0]["modelCode"], "wan2.6-t2i")
        self.assertEqual(result[0]["modelCapabilities"], "image,text-to-image")

    def test_model_page_does_not_use_profile_model_type_filter(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        self.session.add(
            AiModel(provider_id=provider.id, code="image-model", name="Image Model", model_type="image", is_active=True)
        )
        self.session.commit()

        result = AiModelService(self.session).page(CrudQuery(page=1, size=10, raw_params={"modelType": "image"}))

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0]["code"], "image-model")

    def test_runtime_fallback_merges_fallback_options_and_preserves_request_options(self):
        primary_provider = AiProvider(
            code="primary",
            name="Primary",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-primary"),
            is_active=True,
        )
        fallback_provider = AiProvider(
            code="fallback",
            name="Fallback",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-fallback"),
            is_active=True,
        )
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
                return {
                    "content": "fallback ok",
                    "raw": {"id": "2"},
                    "usage": {"totalTokens": 5},
                    "requestId": "fallback-req",
                }

        with patch(
            "app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda provider: FakeAdapter(provider)
        ):
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
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertEqual(seen_options["response_format"], {"type": "json_object"})
        self.assertEqual(result["parsed"], {"ok": True})
        self.assertIsNone(result["parseError"])

    def test_profile_json_schema_response_format_is_normalized_and_passed_to_chat_options(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(profile_code=profile.code, messages=[{"role": "user", "content": "hi"}])
            )

        self.assertEqual(seen_options["response_format"]["type"], "json_schema")
        self.assertEqual(seen_options["response_format"]["json_schema"]["name"], "answer_schema")
        self.assertEqual(
            seen_options["response_format"]["json_schema"]["schema"]["properties"]["answer"]["type"], "string"
        )
        self.assertEqual(result["parsed"], {"answer": "ok"})

    def test_runtime_request_response_format_overrides_profile(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(
                AiChatRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    response_format=AiResponseFormatRequest(type="json_object"),
                )
            )

        self.assertEqual(seen_options["response_format"], {"type": "json_object"})

    def test_runtime_structured_output_parse_error_does_not_fail_call(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

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
        models = self.session.exec(select(AiModel).where(AiModel.provider_id == provider.id)).all()
        image_model = next(item for item in models if item.code == "wan2.6-t2i")
        self.assertEqual(image_model.model_type, "image")
        self.assertEqual(image_model.capabilities, "image,text-to-image")

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
        provider = AiProvider(
            code="deepseek",
            name="Deleted DeepSeek",
            adapter="deepseek",
            base_url="https://old.example.com",
            is_active=False,
            delete_time=datetime.now(UTC),
        )
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="deepseek-v4-flash",
            name="Deleted Model",
            model_type="chat",
            is_active=False,
            delete_time=datetime.now(UTC),
        )
        self.session.add(model)
        self.session.commit()

        result = service.import_catalog(AiCatalogImportRequest(provider_code="deepseek"))
        page = service.page(CrudQuery(page=1, size=10))
        restored = self.session.exec(select(AiProvider).where(AiProvider.code == "deepseek")).first()
        restored_model = self.session.exec(
            select(AiModel).where(AiModel.provider_id == restored.id, AiModel.code == "deepseek-v4-flash")
        ).first()

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
                return iter(
                    [
                        'data: {"choices":[{"delta":{"content":"hi"}}]}',
                        "",
                        "data: [DONE]",
                        "",
                    ]
                )

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(
                adapter.stream_chat(model="qwen-plus", messages=[{"role": "user", "content": "hi"}], options={})
            )

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

    def test_openai_compatible_adapter_image_returns_request_id_and_usage_shape(self):
        provider = AiProvider(
            code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk")
        )
        adapter = OpenAICompatibleAdapter(provider)

        class FakeImageResponse:
            _request_id = "img-req-1"

            def model_dump(self, mode="json"):
                return {
                    "created": 123,
                    "data": [{"url": "https://example.com/a.png"}],
                    "usage": {"total_tokens": 8},
                }

        with patch.object(adapter.client.images, "generate", return_value=FakeImageResponse()):
            result = adapter.image(model="gpt-image-1", prompt="draw", options={"response_format": "url"})

        self.assertEqual(result["requestId"], "img-req-1")
        self.assertEqual(result["usage"]["totalTokens"], 8)
        self.assertEqual(result["data"][0]["url"], "https://example.com/a.png")

    def test_openai_compatible_adapter_image_returns_none_request_id_when_missing(self):
        provider = AiProvider(
            code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk")
        )
        adapter = OpenAICompatibleAdapter(provider)

        class FakeImageResponse:
            def model_dump(self, mode="json"):
                return {"data": [{"b64_json": "abc"}]}

        with patch.object(adapter.client.images, "generate", return_value=FakeImageResponse()):
            result = adapter.image(model="gpt-image-1", prompt="draw", options={"response_format": "b64_json"})

        self.assertIsNone(result["requestId"])
        self.assertEqual(result["usage"], {})
        self.assertEqual(result["data"][0]["b64_json"], "abc")

    def test_openai_compatible_adapter_disables_sdk_retries_by_default(self):
        # OpenAI SDK 默认 max_retries=2 会在超时/5xx 静默重试；同步计费接口无幂等键，
        # 重试即重复扣费，默认必须关闭，仅 extra_config.max_retries 显式开启
        provider = AiProvider(
            code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk")
        )
        self.assertEqual(OpenAICompatibleAdapter(provider).client.max_retries, 0)

        retry_provider = AiProvider(
            code="openai-retry",
            name="OpenAI Retry",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk"),
            extra_config=json.dumps({"max_retries": 3}),
        )
        self.assertEqual(OpenAICompatibleAdapter(retry_provider).client.max_retries, 3)

    def test_openai_compatible_adapter_image_filters_nonstandard_options_and_logs_warning(self):
        provider = AiProvider(
            code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk")
        )
        adapter = OpenAICompatibleAdapter(provider)

        class FakeImageResponse:
            _request_id = "img-req-2"

            def model_dump(self, mode="json"):
                return {"data": [{"url": "https://example.com/b.png"}]}

        with self.assertLogs("app.modules.ai.service.adapters.openai_compatible", level="WARNING") as logs:
            with patch.object(adapter.client.images, "generate", return_value=FakeImageResponse()) as mocked:
                result = adapter.image(
                    model="gpt-image-1",
                    prompt="draw",
                    options={"response_format": "url", "watermark": True, "size": "1024x1024"},
                )

        self.assertEqual(result["requestId"], "img-req-2")
        self.assertEqual(
            mocked.call_args.kwargs,
            {"model": "gpt-image-1", "prompt": "draw", "response_format": "url", "size": "1024x1024"},
        )
        self.assertTrue(any("已拦截非标准字段" in message for message in logs.output))

    def test_openai_compatible_adapter_gpt_image_2_constraints(self):
        provider = AiProvider(
            code="openai", name="OpenAI", adapter="openai-compatible", api_key_cipher=encrypt_secret("sk")
        )
        adapter = OpenAICompatibleAdapter(provider)

        class FakeImageResponse:
            _request_id = "gpt-image-2-req"

            def model_dump(self, mode="json"):
                return {"data": [{"b64_json": "fake-b64"}]}

        with patch.object(adapter.client.images, "generate", return_value=FakeImageResponse()) as mocked:
            result = adapter.image(
                model="gpt-image-2-something",
                prompt="draw",
                options={"n": 3, "response_format": "url", "thinking": True, "size": "1024x1024"},
            )

        self.assertEqual(result["requestId"], "gpt-image-2-req")
        self.assertEqual(result["data"][0]["b64_json"], "fake-b64")
        expected_kwargs = {
            "model": "gpt-image-2-something",
            "prompt": "draw",
            "size": "1024x1024",
            "n": 1,
            "response_format": "b64_json",
            "extra_body": {"thinking": True},
        }
        self.assertEqual(mocked.call_args.kwargs, expected_kwargs)

    def test_qianfan_adapter_irag_1_0_constraints(self):
        provider = AiProvider(code="qianfan", name="百度千帆", adapter="qianfan", api_key_cipher=encrypt_secret("sk"))
        adapter = QianfanAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "qianfan-req-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"url": "https://example.com/qianfan.png"}]}

        long_prompt = "a" * 250
        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            result = adapter.image(
                model="irag-1.0",
                prompt=long_prompt,
                options={
                    "negative_prompt": "ugly",
                    "seed": 123,
                    "image": "https://example.com/input.png",
                    "size": "1024x1024",
                },
            )

        self.assertEqual(result["requestId"], "qianfan-req-1")
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "irag-1.0")
        self.assertEqual(payload["prompt"], "a" * 220)
        self.assertNotIn("negative_prompt", payload)
        self.assertNotIn("seed", payload)
        self.assertNotIn("image", payload)
        self.assertEqual(payload["refer_image"], "https://example.com/input.png")
        self.assertEqual(payload["size"], "1024x1024")

        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            adapter.image(
                model="other-qianfan-model",
                prompt="draw",
                options={"image": "https://example.com/input.png", "refer_image": "https://example.com/input.png"},
            )
        payload = mocked.call_args.kwargs["json"]
        self.assertNotIn("image", payload)
        self.assertNotIn("refer_image", payload)

    def test_gemini_adapter_image_generation(self):
        provider = AiProvider(
            code="gemini", name="Google Gemini", adapter="gemini", api_key_cipher=encrypt_secret("sk")
        )
        adapter = GeminiAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "gemini-img-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"inlineData": {"mimeType": "image/png", "data": "fake-b64-image-bytes"}}]
                            }
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30},
                }

        with patch("httpx.post", return_value=FakeResponse()) as mocked_post:
            result = adapter.image(
                model="imagen-3.0-generate-002",
                prompt="a beautiful cat",
                options={"aspectRatio": "1:1", "number_of_images": 1},
            )

        self.assertEqual(result["requestId"], "gemini-img-req")
        self.assertEqual(result["data"][0]["b64_json"], "fake-b64-image-bytes")
        self.assertEqual(result["usage"]["totalTokens"], 30)

        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["contents"][0]["parts"], [{"text": "a beautiful cat"}])
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["TEXT", "IMAGE"])
        self.assertEqual(payload["generationConfig"]["aspectRatio"], "1:1")
        self.assertEqual(payload["generationConfig"]["number_of_images"], 1)

        with patch("httpx.post", return_value=FakeResponse()) as mocked_post:
            adapter.image(
                model="imagen-3.0-generate-002",
                prompt="make it red",
                options={"image": "data:image/png;base64,abcdefg"},
            )
        payload = mocked_post.call_args.kwargs["json"]
        parts = payload["contents"][0]["parts"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], {"inlineData": {"mimeType": "image/png", "data": "abcdefg"}})
        self.assertEqual(parts[1], {"text": "make it red"})

        class FakeStreamResponse:
            headers = {"content-type": "image/jpeg", "content-length": "15"}
            is_redirect = False

            def raise_for_status(self):
                return None

            def iter_bytes(self, chunk_size=8192):
                yield b"fake-jpeg-bytes"

        class FakeStreamContext:
            def __init__(self, method, url, *args, **kwargs):
                self.method = method
                self.url = url
                self.args = args
                self.kwargs = kwargs

            def __enter__(self):
                return FakeStreamResponse()

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        with (
            patch("app.modules.ai.service.adapters.gemini.safe_stream", side_effect=FakeStreamContext) as mocked_stream,
            patch("httpx.post", return_value=FakeResponse()) as mocked_post,
            patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]),
        ):
            adapter.image(
                model="imagen-3.0-generate-002",
                prompt="style of this",
                options={"image": "https://example.com/style.jpg"},
            )
        mocked_stream.assert_called_once()
        call_args = mocked_stream.call_args
        self.assertEqual(call_args.args[0], "GET")
        # SSRF 防护：URL 中 hostname 被替换为已校验的 IP
        self.assertIn("93.184.216.34", call_args.args[1])
        # SNI 修复：原 hostname 作为第 3 位置参数传入 safe_stream，用于 TLS 证书/SNI 校验
        self.assertEqual(call_args.args[2], "example.com")
        self.assertEqual(call_args.kwargs["headers"]["Host"], "example.com")
        self.assertEqual(call_args.kwargs["timeout"], 15)
        self.assertEqual(call_args.kwargs["follow_redirects"], False)
        payload = mocked_post.call_args.kwargs["json"]
        parts = payload["contents"][0]["parts"]
        import base64

        expected_b64 = base64.b64encode(b"fake-jpeg-bytes").decode("utf-8")
        self.assertEqual(parts[0], {"inlineData": {"mimeType": "image/jpeg", "data": expected_b64}})

    def test_bailian_adapter_wan26_sync_image_normalizes_payload_and_result(self):
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "bailian-sync-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"choices": [{"message": {"content": [{"image": "https://example.com/wan26.png"}]}}]}}

        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            result = adapter.image(model="wan2.6-t2i", prompt="draw", options={"size": "1024x1024", "watermark": False})

        self.assertEqual(
            str(mocked.call_args.args[0]),
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        )
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "wan2.6-t2i")
        self.assertEqual(payload["input"]["messages"][0]["content"][0]["text"], "draw")
        self.assertEqual(payload["parameters"]["size"], "1024*1024")
        self.assertFalse(payload["parameters"]["watermark"])
        self.assertEqual(result["data"][0]["url"], "https://example.com/wan26.png")
        self.assertEqual(result["requestId"], "bailian-sync-1")

    def test_bailian_adapter_wan26_sync_rejects_negative_prompt(self):
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        # AI-009：参数组合错误抛 AdapterInputError（领域异常），运行时不降级不重试
        with self.assertRaises(AdapterInputError) as ctx:
            adapter.image(model="wan2.6-t2i", prompt="draw", options={"negative_prompt": "blur"})

        self.assertIn("negative_prompt", str(ctx.exception))

    def test_bailian_adapter_wan26_async_keeps_negative_prompt(self):
        provider = AiProvider(
            code="bailian",
            name="百炼",
            adapter="bailian",
            api_key_cipher=encrypt_secret("sk"),
            extra_config='{"image_poll_interval_seconds":0,"image_poll_timeout_seconds":1}',
        )
        adapter = BailianAdapter(provider)

        class PostResponse:
            headers = {"x-request-id": "create-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"task_id": "task-1"}}

        class GetResponse:
            headers = {"x-request-id": "poll-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "output": {"task_status": "SUCCEEDED", "results": [{"url": "https://example.com/wan26-async.png"}]}
                }

        with patch("httpx.post", return_value=PostResponse()) as mocked_post:
            with patch("httpx.get", return_value=GetResponse()):
                result = adapter.image(
                    model="wan2.6-t2i", prompt="draw", options={"async": True, "negativePrompt": "blur"}
                )

        self.assertEqual(
            str(mocked_post.call_args.args[0]),
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation",
        )
        self.assertEqual(mocked_post.call_args.kwargs["headers"]["X-DashScope-Async"], "enable")
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["input"]["negative_prompt"], "blur")
        self.assertNotIn("negative_prompt", payload["parameters"])
        self.assertEqual(result["data"][0]["url"], "https://example.com/wan26-async.png")

    def test_bailian_adapter_legacy_async_image_polls_task_and_uses_workspace(self):
        provider = AiProvider(
            code="bailian",
            name="百炼",
            adapter="bailian",
            api_key_cipher=encrypt_secret("sk"),
            extra_config='{"workspace_id":"ws-1","image_poll_interval_seconds":0,"image_poll_timeout_seconds":1}',
        )
        adapter = BailianAdapter(provider)

        class PostResponse:
            headers = {"x-request-id": "create-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"task_id": "task-1"}}

        class GetResponse:
            headers = {"x-request-id": "poll-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"task_status": "SUCCEEDED", "results": [{"url": "https://example.com/legacy.png"}]}}

        with patch("httpx.post", return_value=PostResponse()) as mocked_post:
            with patch("httpx.get", return_value=GetResponse()) as mocked_get:
                result = adapter.image(
                    model="wan2.5-t2i-preview", prompt="draw", options={"size": "1024x1024", "negative_prompt": "blur"}
                )

        self.assertEqual(
            str(mocked_post.call_args.args[0]),
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        )
        self.assertEqual(mocked_post.call_args.kwargs["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(mocked_post.call_args.kwargs["headers"]["X-DashScope-WorkSpace"], "ws-1")
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["input"]["prompt"], "draw")
        self.assertEqual(payload["input"]["negative_prompt"], "blur")
        self.assertEqual(payload["parameters"]["size"], "1024*1024")
        self.assertEqual(str(mocked_get.call_args.args[0]), "https://dashscope.aliyuncs.com/api/v1/tasks/task-1")
        self.assertEqual(result["data"][0]["url"], "https://example.com/legacy.png")
        self.assertEqual(result["taskId"], "task-1")
        self.assertEqual(result["requestId"], "poll-req")

    def test_bailian_adapter_async_image_failure_includes_task_id(self):
        provider = AiProvider(
            code="bailian",
            name="百炼",
            adapter="bailian",
            api_key_cipher=encrypt_secret("sk"),
            extra_config='{"image_poll_interval_seconds":0,"image_poll_timeout_seconds":1}',
        )
        adapter = BailianAdapter(provider)

        class PostResponse:
            headers = {"x-request-id": "create-req"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"task_id": "task-failed"}}

        class GetResponse:
            headers = {"x-request-id": "poll-failed"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"output": {"task_status": "FAILED", "message": "bad prompt"}}

        with patch("httpx.post", return_value=PostResponse()):
            with patch("httpx.get", return_value=GetResponse()):
                with self.assertRaises(Exception) as ctx:
                    adapter.image(model="wan2.2-t2i-flash", prompt="draw", options={})

        self.assertIn("bad prompt", str(ctx.exception))
        self.assertIn("task-failed", str(ctx.exception))

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
            result = adapter.chat(
                model="deepseek-v4-flash", messages=[{"role": "user", "content": "hi"}], options={"temperature": 0.2}
            )

        self.assertEqual(result["content"], "deepseek ok")
        self.assertEqual(result["usage"]["totalTokens"], 7)
        self.assertEqual(result["requestId"], "ds-req-1")
        self.assertEqual(str(mocked.call_args.args[0]), "https://api.deepseek.com/chat/completions")
        self.assertEqual(mocked.call_args.kwargs["json"]["model"], "deepseek-v4-flash")

    def test_deepseek_adapter_chat_downgrades_json_schema_response_format(self):
        """DeepSeek chat/completions 不支持 json_schema，须降级为 json_object（否则 400）。"""
        provider = AiProvider(code="deepseek", name="DeepSeek", adapter="deepseek", api_key_cipher=encrypt_secret("sk"))
        adapter = DeepSeekAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "ds-req-2"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

        json_schema_format = {
            "type": "json_schema",
            "json_schema": {"name": "plan", "schema": {"type": "object"}, "strict": True},
        }
        with patch("httpx.post", return_value=FakeResponse()) as mocked:
            adapter.chat(
                model="deepseek-v4-flash",
                messages=[{"role": "user", "content": "输出 json"}],
                options={"response_format": json_schema_format, "temperature": 0.3},
            )

        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        # JSON 模式注入 thinking=disabled，避免思维链耗尽 max_tokens 导致 content 为空
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["temperature"], 0.3)
        # 原 options 不被原地修改
        self.assertEqual(json_schema_format["type"], "json_schema")

    def test_adapt_deepseek_options_keeps_other_cases(self):
        self.assertEqual(_adapt_deepseek_options(None), {})
        # 无 response_format 的普通调用不受影响
        self.assertEqual(_adapt_deepseek_options({"temperature": 0.5}), {"temperature": 0.5})
        # 显式设置 thinking 时尊重调用方选择
        self.assertEqual(
            _adapt_deepseek_options({"response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}}),
            {"response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}},
        )
        adapted = _adapt_deepseek_options({"response_format": {"type": "json_schema", "json_schema": {}}})
        self.assertEqual(adapted["response_format"], {"type": "json_object"})
        self.assertEqual(adapted["thinking"], {"type": "disabled"})

    def test_volcengine_adapter_image_defaults_url_and_passes_options(self):
        provider = AiProvider(
            code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk")
        )
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
        provider = AiProvider(
            code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk")
        )
        adapter = VolcengineArkAdapter(provider)

        class FakeResponse:
            headers = {"x-tt-logid": "tt-log-1"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"result": {"images": [{"image_url": "https://example.com/custom.png"}, {"base64": "abc"}]}}

        with patch("httpx.post", return_value=FakeResponse()):
            result = adapter.image(
                model="doubao-seedream-5.0-lite", prompt="draw", options={"response_format": "b64_json"}
            )

        self.assertEqual(result["data"][0]["url"], "https://example.com/custom.png")
        self.assertEqual(result["data"][1]["b64_json"], "abc")
        self.assertEqual(result["requestId"], "tt-log-1")

    def test_volcengine_adapter_image_exposes_upstream_error_body(self):
        provider = AiProvider(
            code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk")
        )
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
        provider = AiProvider(
            code="volc", name="火山方舟", adapter="volcengine-ark", api_key_cipher=encrypt_secret("sk")
        )
        adapter = VolcengineArkAdapter(provider)

        # AI-009：参数错误抛 AdapterInputError（领域异常），运行时不降级不重试
        with self.assertRaises(AdapterInputError) as ctx:
            adapter.image(model="doubao-seedream-4-5-251128", prompt="draw", options={"size": "1536x1536"})

        self.assertIn("3686400", str(ctx.exception))

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
                return iter(
                    [
                        "event: content_block_delta",
                        'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"think"}}',
                        "",
                        "event: content_block_delta",
                        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}',
                        "",
                        "event: message_stop",
                        'data: {"type":"message_stop"}',
                        "",
                    ]
                )

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(
                adapter.stream_chat(model="claude-test", messages=[{"role": "user", "content": "hi"}], options={})
            )

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
                return iter(
                    [
                        'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}],"usageMetadata":{"totalTokenCount":3}}',
                        "",
                    ]
                )

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(
                adapter.stream_chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}], options={})
            )

        self.assertEqual(events[0]["event"], "delta")
        self.assertEqual(events[0]["content"], "hello")

    def test_ollama_adapter_stream_chat_parses_ndjson_delta(self):
        provider = AiProvider(code="ollama", name="Ollama", adapter="ollama")
        adapter = OllamaAdapter(provider)

        class FakeStreamResponse:
            headers = {"x-request-id": "req-ollama-test"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter(
                    [
                        json.dumps({"message": {"content": "hi"}, "done": False}),
                        json.dumps({"done": True, "prompt_eval_count": 1, "eval_count": 2}),
                    ]
                )

        with patch("httpx.stream", return_value=FakeStreamResponse()):
            events = list(adapter.stream_chat(model="llama", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(events[0]["event"], "delta")
        self.assertEqual(events[0]["content"], "hi")
        self.assertEqual(events[-1]["usage"]["totalTokens"], 3)
        # 上游请求标识头须逐事件透传供审计回收（P3 遗留）
        self.assertEqual(events[0]["requestId"], "req-ollama-test")
        self.assertEqual(events[-1]["requestId"], "req-ollama-test")

    def test_ollama_adapter_sends_auth_header(self):
        """配置了 api_key 时（如经鉴权网关暴露），请求必须携带鉴权头而非静默忽略。"""
        provider = AiProvider(
            code="ollama", name="Ollama", adapter="ollama", api_key_cipher=encrypt_secret("sk-ollama")
        )
        adapter = OllamaAdapter(provider)

        class FakeStreamResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter([json.dumps({"done": True})])

        with patch("httpx.stream", return_value=FakeStreamResponse()) as mock_stream:
            list(adapter.stream_chat(model="llama", messages=[{"role": "user", "content": "hi"}], options={}))

        headers = mock_stream.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer sk-ollama")

    def test_with_heartbeat_emits_sentinel_during_silence(self):
        def slow_events():
            yield {"event": "delta", "content": "a"}
            time.sleep(0.15)
            yield {"event": "delta", "content": "b"}

        items = list(_with_heartbeat(slow_events(), interval=0.05))

        self.assertEqual(items[0], {"event": "delta", "content": "a"})
        self.assertEqual(items[-1], {"event": "delta", "content": "b"})
        heartbeats = [item for item in items if item is _STREAM_HEARTBEAT]
        self.assertGreaterEqual(len(heartbeats), 1)

    def test_with_heartbeat_passthrough_without_silence(self):
        def fast_events():
            yield {"seq": 1}
            yield {"seq": 2}

        items = list(_with_heartbeat(fast_events(), interval=5.0))

        self.assertEqual(items, [{"seq": 1}, {"seq": 2}])

    def test_with_heartbeat_propagates_upstream_error(self):
        def bad_events():
            yield {"seq": 1}
            raise RuntimeError("upstream boom")

        with self.assertRaises(RuntimeError):
            list(_with_heartbeat(bad_events(), interval=5.0))

    def test_with_heartbeat_stops_pump_after_close(self):
        started = threading.Event()

        def endless_events():
            started.set()
            while True:
                time.sleep(0.01)
                yield {"tick": True}

        stream = _with_heartbeat(endless_events(), interval=5.0)
        self.assertEqual(next(stream), {"tick": True})
        # 模拟客户端断开：生成器关闭后 pump 线程须随 stop 标志退出
        stream.close()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not any(t.name == "ai-stream-heartbeat-pump" for t in threading.enumerate()):
                break
            time.sleep(0.02)
        self.assertFalse(any(t.name == "ai-stream-heartbeat-pump" for t in threading.enumerate()))

    def test_runtime_stream_chat_does_not_touch_request_session(self):
        """P1 回归：流式生成器在线程池迭代，不得复用非线程安全的请求会话做 DB 操作。"""
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
        self.session.commit()

        in_stream = {"active": False}
        request_session = self.session
        touched: list[str] = []

        def _spy(method_name: str):
            original = getattr(request_session, method_name)

            def wrapper(*args, **kwargs):
                if in_stream["active"]:
                    touched.append(method_name)
                return original(*args, **kwargs)

            return wrapper

        for name in ("add", "commit", "flush", "execute", "exec", "get"):
            setattr(request_session, name, _spy(name))

        class FakeAdapter:
            def stream_chat(self, *, model, messages, options):
                yield {"event": "delta", "content": "he"}
                # begin 已在首事件前执行；此后到收尾之间请求会话必须零参与
                in_stream["active"] = True
                yield {"event": "delta", "content": "llo"}
                yield {"event": "done", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            chunks = list(
                AiModelRuntimeService(self.session).stream_chat(
                    AiChatRequest(messages=[{"role": "user", "content": "hi"}])
                )
            )

        in_stream["active"] = False
        events = _parse_sse_chunks(chunks)
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(touched, [])

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
        model = AiModel(
            provider_id=provider.id, code="image-test", name="Image Test", model_type="image", is_active=True
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="image-default",
            name="Image Default",
            model_id=model.id,
            scenario="default",
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()

        with self.assertRaises(HTTPException) as ctx:
            AiModelRuntimeService(self.session).image(AiImageRequest(prompt="draw"))

        self.assertEqual(ctx.exception.status_code, 501)

    def test_runtime_profile_timeout_applies_to_adapter(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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
            timeout=7,
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            timeout = 60

            def chat(self, *, model, messages, options):
                return {"content": "ok", "raw": {"timeout": self.timeout}, "usage": {}}

        adapter = FakeAdapter()
        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=adapter):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertEqual(result["raw"]["timeout"], 7.0)
        self.assertEqual(adapter.timeout, 60)

    def test_ai_generation_task_submit_and_execute_success(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
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
        self.session.commit()

        class FakeAsyncResult:
            id = "celery-1"

        with patch(
            "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.apply_async",
            return_value=FakeAsyncResult(),
        ):
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

        with (
            patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()),
            patch("app.modules.ai.tasks.generation_tasks.engine", self.engine),
        ):
            result = execute_ai_generation_task.run(task.id)

        self.assertTrue(result["success"])
        saved = self.session.get(AiGenerationTask, task.id)
        self.session.refresh(saved)
        self.assertEqual(saved.status, "success")
        self.assertEqual(saved.progress, 100)
        self.assertIn("ok", saved.result_payload)

    def test_ai_generation_task_uses_isolated_queue_and_declares_worker_queues(self):
        provider = AiProvider(
            code="openai",
            name="OpenAI",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id, code="image-test", name="Image Test", model_type="image", is_active=True
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-image", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()

        class FakeAsyncResult:
            id = "celery-image-1"

        with patch(
            "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.apply_async",
            return_value=FakeAsyncResult(),
        ) as mocked:
            AiGenerationTaskService(self.session).submit(
                AiTaskSubmitRequest(task_type="image", payload={"prompt": "hi"})
            )

        self.assertEqual(mocked.call_args.kwargs["queue"], "ai.image")
        declared_queues = {queue.name for queue in celery_app.conf.task_queues}
        self.assertIn("default", declared_queues)
        self.assertTrue(set(AI_TASK_QUEUES).issubset(declared_queues))

    def test_sync_models_marks_new_models_inactive_and_pending_manual_classification(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)

        with patch("app.modules.ai.service.provider_service.build_adapter") as build_adapter_mock:
            build_adapter_mock.return_value.list_models.return_value = [
                {"code": "new-image-model", "name": "New Image Model"}
            ]
            result = AiProviderService(self.session).sync_models(provider.id)

        saved = self.session.exec(
            select(AiModel).where(AiModel.provider_id == provider.id, AiModel.code == "new-image-model")
        ).one()
        self.assertTrue(result["success"])
        self.assertFalse(saved.is_active)
        self.assertEqual(saved.model_type, "chat")
        self.assertEqual(saved.capabilities, "sync-pending,manual-classification-required")

    def test_ai_generation_task_submit_marks_failed_when_enqueue_fails(self):
        with patch(
            "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.apply_async",
            side_effect=RuntimeError("broker down"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                AiGenerationTaskService(self.session).submit(
                    AiTaskSubmitRequest(task_type="chat", payload={"messages": []})
                )

        self.assertEqual(ctx.exception.status_code, 503)
        task = self.session.exec(select(AiGenerationTask)).one()
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.progress, 100)
        self.assertIn("broker down", task.error_message)
        self.assertIsNone(task.celery_task_id)

    def test_ai_generation_task_does_not_overwrite_cancelled_after_runtime(self):
        task = AiGenerationTask(
            task_type="chat", request_payload='{"messages":[{"role":"user","content":"hi"}]}', status="pending"
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        def cancel_during_call(session: Session, running_task: AiGenerationTask, payload: dict) -> dict:
            running_task.status = "cancelled"
            running_task.finished_at = datetime.now(UTC)
            session.add(running_task)
            session.commit()
            return {"content": "late result"}

        with (
            patch("app.modules.ai.tasks.generation_tasks.engine", self.engine),
            patch("app.modules.ai.tasks.generation_tasks._invoke_runtime", side_effect=cancel_during_call),
        ):
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

        with patch(
            "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task.apply_async",
            return_value=FakeAsyncResult(),
        ):
            retry = AiGenerationTaskService(self.session).retry(task.id)
        self.assertTrue(retry["success"])
        self.session.refresh(task)
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.retry_count, 1)

        cancel = AiGenerationTaskService(self.session).cancel(task.id)
        self.assertTrue(cancel["success"])
        self.session.refresh(task)
        self.assertEqual(task.status, "cancelled")

    def test_governance_global_request_limit_blocks_runtime(self):
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

        with self.assertRaises(HTTPException) as ctx:
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(ctx.exception.status_code, 429)
        event = self.session.exec(select(AiGovernanceEvent)).one()
        self.assertEqual(event.event_type, "blocked")
        self.assertEqual(event.metric, "request")

    def test_governance_concurrent_limit_releases_after_call(self):
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
                code="conc-one",
                name="Concurrent One",
                scope_type="profile",
                profile_id=profile.id,
                period="day",
                max_concurrent=1,
                is_active=True,
            )
        )
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            first = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )
            second = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])

    def test_governance_cost_calculation_records_log_cost(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="gpt-test",
            name="GPT Test",
            model_type="chat",
            pricing_config='{"input_per_1m": 2, "output_per_1m": 4}',
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {
                    "content": "ok",
                    "usage": {"promptTokens": 1_000_000, "completionTokens": 500_000, "totalTokens": 1_500_000},
                }

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.cost_micro_usd, 4_000_000)

    def test_governance_token_limit_blocks_before_adapter_call(self):
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
                code="token-rule", name="Token Rule", scope_type="global", period="day", max_tokens=100, is_active=True
            )
        )
        self.session.add(
            AiModelCallLog(
                provider_id=provider.id,
                model_id=model.id,
                profile_id=profile.id,
                model_type="chat",
                status="success",
                total_tokens=100,
            )
        )
        self.session.commit()

        with patch("app.modules.ai.service.runtime_service.build_adapter") as mocked_build_adapter:
            with self.assertRaises(HTTPException) as ctx:
                AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(ctx.exception.status_code, 429)
        mocked_build_adapter.assert_not_called()
        event = self.session.exec(select(AiGovernanceEvent)).one()
        self.assertEqual(event.event_type, "blocked")
        self.assertEqual(event.metric, "token")

    def test_governance_cost_limit_blocks_before_adapter_call(self):
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
                code="cost-rule",
                name="Cost Rule",
                scope_type="global",
                period="day",
                max_cost_micro_usd=100,
                is_active=True,
            )
        )
        self.session.add(
            AiModelCallLog(
                provider_id=provider.id,
                model_id=model.id,
                profile_id=profile.id,
                model_type="chat",
                status="success",
                cost_micro_usd=100,
            )
        )
        self.session.commit()

        with patch("app.modules.ai.service.runtime_service.build_adapter") as mocked_build_adapter:
            with self.assertRaises(HTTPException) as ctx:
                AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(ctx.exception.status_code, 429)
        mocked_build_adapter.assert_not_called()
        event = self.session.exec(select(AiGovernanceEvent)).one()
        self.assertEqual(event.event_type, "blocked")
        self.assertEqual(event.metric, "cost")

    def test_governance_observe_token_limit_records_event_without_blocking(self):
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
                code="observe-token-rule",
                name="Observe Token Rule",
                scope_type="global",
                period="day",
                max_tokens=100,
                mode="observe",
                is_active=True,
            )
        )
        self.session.add(
            AiModelCallLog(
                provider_id=provider.id,
                model_id=model.id,
                profile_id=profile.id,
                model_type="chat",
                status="success",
                total_tokens=100,
            )
        )
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        with patch(
            "app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()
        ) as mocked_build_adapter:
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertTrue(result["success"])
        mocked_build_adapter.assert_called_once()
        events = self.session.exec(select(AiGovernanceEvent)).all()
        self.assertTrue(any(event.event_type == "blocked" and event.metric == "token" for event in events))

    def test_governance_post_usage_does_not_double_count_current_call(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="gpt-test",
            name="GPT Test",
            model_type="chat",
            pricing_config='{"input_per_1m": 1, "output_per_1m": 1}',
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.add(
            AiGovernanceRule(
                code="token-rule", name="Token Rule", scope_type="global", period="day", max_tokens=100, is_active=True
            )
        )
        self.session.add(
            AiGovernanceRule(
                code="cost-rule",
                name="Cost Rule",
                scope_type="global",
                period="day",
                max_cost_micro_usd=100,
                is_active=True,
            )
        )
        self.session.commit()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"promptTokens": 30, "completionTokens": 30, "totalTokens": 60}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(len(self.session.exec(select(AiModelCallLog)).all()), 1)
        self.assertEqual(len(self.session.exec(select(AiGovernanceEvent)).all()), 0)

    def test_provider_sync_models_creates_inactive_new_models(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)

        class FakeAdapter:
            def list_models(self):
                return [{"code": "new-model", "name": "New Model"}]

        with patch("app.modules.ai.service.provider_service.build_adapter", return_value=FakeAdapter()):
            result = AiProviderService(self.session).sync_models(provider.id)

        self.assertEqual(result["created"], 1)
        model = self.session.exec(select(AiModel).where(AiModel.code == "new-model")).one()
        self.assertFalse(model.is_active)

    def test_governance_cleanup_clears_payload_and_deletes_old_logs(self):
        old = datetime.now(UTC).replace(year=2020)
        task = AiGenerationTask(task_type="chat", request_payload='{"x":1}', result_payload='{"y":2}', status="success")
        log = AiModelCallLog(model_type="chat", status="success")
        event = AiGovernanceEvent(event_type="blocked", metric="request")
        self.session.add(task)
        self.session.add(log)
        self.session.add(event)
        self.session.commit()
        task.created_at = old
        log.created_at = old
        event.created_at = old
        self.session.add(task)
        self.session.add(log)
        self.session.add(event)
        self.session.commit()

        result = AiGovernanceCleanupService(self.session).clean(90, 180, 180)

        self.assertEqual(result["taskPayloadCleared"], 1)
        self.session.refresh(task)
        self.assertIsNone(task.request_payload)
        self.assertIsNone(task.result_payload)
        self.assertEqual(len(self.session.exec(select(AiModelCallLog)).all()), 0)
        self.assertEqual(len(self.session.exec(select(AiGovernanceEvent)).all()), 0)

    def test_volcengine_ark_adapter_image_includes_image_payload(self):
        provider = AiProvider(code="volcengine", name="Volcengine", adapter="volcengine-ark", is_active=True)
        from app.modules.ai.service.adapters.factory import VolcengineArkAdapter

        adapter = VolcengineArkAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "req-1"}

        with patch.object(adapter, "_post", return_value=({}, FakeResponse())) as mocked_post:
            adapter.image(
                model="doubao-seedream-5.0-lite", prompt="draw", options={"image": "https://example.com/test.jpg"}
            )

        self.assertEqual(mocked_post.call_args[0][0], adapter.images_path)
        payload = mocked_post.call_args[0][1]
        self.assertEqual(payload["image"], "https://example.com/test.jpg")

    def test_bailian_adapter_qwen_image_sync_multimodal_payload(self):
        provider = AiProvider(code="bailian", name="Bailian", adapter="bailian", is_active=True)
        from app.modules.ai.service.adapters.factory import BailianAdapter

        adapter = BailianAdapter(provider)

        class FakeResponse:
            headers = {"x-request-id": "req-1"}

        with patch.object(adapter, "_post_dashscope", return_value=({}, FakeResponse())) as mocked_post:
            adapter.image(
                model="qwen-image-2.0",
                prompt="draw",
                options={
                    "image": ["https://example.com/1.jpg", "https://example.com/2.jpg"],
                    "negative_prompt": "blurry",
                },
            )

        self.assertEqual(mocked_post.call_args[0][0], "/services/aigc/multimodal-generation/generation")
        payload = mocked_post.call_args[0][1]
        self.assertEqual(payload["model"], "qwen-image-2.0")
        messages = payload["input"]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")

        content = messages[0]["content"]
        self.assertEqual(content[0], {"image": "https://example.com/1.jpg"})
        self.assertEqual(content[1], {"image": "https://example.com/2.jpg"})
        self.assertEqual(content[2], {"text": "draw"})

        parameters = payload["parameters"]
        self.assertEqual(parameters["negative_prompt"], "blurry")

    def test_openai_compatible_adapter_image_passes_extra_body(self):
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter

        adapter = OpenAICompatibleAdapter(provider)

        class FakeImageResponse:
            def model_dump(self, mode="json"):
                return {"data": []}

        with patch.object(adapter.client.images, "generate", return_value=FakeImageResponse()) as mocked_generate:
            adapter.image(
                model="gpt-image-2-custom",
                prompt="draw",
                options={"image": "https://example.com/ref.png", "size": "1024x1024"},
            )

        kwargs = mocked_generate.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-image-2-custom")
        self.assertEqual(kwargs["prompt"], "draw")
        self.assertEqual(kwargs["size"], "1024x1024")

        extra_body = kwargs["extra_body"]
        self.assertEqual(extra_body["image"], "https://example.com/ref.png")

    def test_call_log_persists_request_options_and_sanitizes(self):
        provider = AiProvider(
            code="test-log-options-p",
            name="Test Provider",
            adapter="openai-compatible",
            api_key_cipher=encrypt_secret("sk-test"),
            is_active=True,
        )
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="test-log-options-m",
            name="Test Model",
            model_type="chat",
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="test-log-options-prof",
            name="Test Profile",
            model_id=model.id,
            scenario="default",
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()

        class DummyAdapter:
            def __init__(self, provider):
                pass

            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"totalTokens": 10}, "requestId": "req-1"}

        with patch("app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda p: DummyAdapter(p)):
            AiModelRuntimeService(self.session).chat(
                AiChatRequest(
                    profile_code=profile.code,
                    messages=[{"role": "user", "content": "hello"}],
                    options={"temperature": 0.8, "api_key": "secret_key"},
                )
            )

        log = self.session.exec(select(AiModelCallLog).where(AiModelCallLog.profile_id == profile.id)).first()
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.request_options)
        import json

        saved_options = json.loads(log.request_options)
        self.assertEqual(saved_options["temperature"], 0.8)
        self.assertEqual(saved_options["api_key"], "***")

    def test_runtime_fallback_preserves_task_id(self):
        p1 = AiProvider(code="fb-p1", name="P1", adapter="openai-compatible", is_active=True)
        p2 = AiProvider(code="fb-p2", name="P2", adapter="openai-compatible", is_active=True)
        self.session.add(p1)
        self.session.add(p2)
        self.session.commit()
        m1 = AiModel(provider_id=p1.id, code="fb-m1", name="M1", model_type="chat", is_active=True)
        m2 = AiModel(provider_id=p2.id, code="fb-m2", name="M2", model_type="chat", is_active=True)
        self.session.add(m1)
        self.session.add(m2)
        self.session.commit()
        prof2 = AiModelProfile(code="fb-prof2", name="Prof2", model_id=m2.id, scenario="default", is_active=True)
        self.session.add(prof2)
        self.session.commit()
        prof1 = AiModelProfile(
            code="fb-prof1",
            name="Prof1",
            model_id=m1.id,
            scenario="default",
            fallback_profile_id=prof2.id,
            is_active=True,
        )
        self.session.add(prof1)
        self.session.commit()

        class FailThenSuccessAdapter:
            def __init__(self, provider):
                self.provider = provider

            def chat(self, *, model, messages, options):
                if self.provider.code == "fb-p1":
                    raise RuntimeError("primary failed")
                return {"content": "fallback success", "usage": {}, "requestId": "r2"}

        with patch(
            "app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda p: FailThenSuccessAdapter(p)
        ):
            AiModelRuntimeService(self.session).chat(
                AiChatRequest(profile_code=prof1.code, messages=[{"role": "user", "content": "hi"}]),
                task_id=9999,
            )

        invocations = self.session.exec(select(AiRuntimeInvocation).where(AiRuntimeInvocation.task_id == 9999)).all()
        self.assertEqual(len(invocations), 2)
        self.assertEqual(invocations[0].profile_id, prof1.id)
        self.assertEqual(invocations[1].profile_id, prof2.id)

    def test_profile_partial_update_is_default_clears_old_default(self):
        from app.modules.ai.service.profile_service import AiModelProfileService

        p = AiProvider(code="prov-def-test", name="P", adapter="openai-compatible", is_active=True)
        self.session.add(p)
        self.session.commit()
        m = AiModel(provider_id=p.id, code="model-def-test", name="M", model_type="chat", is_active=True)
        self.session.add(m)
        self.session.commit()
        prof1 = AiModelProfile(
            code="prof-old-default",
            name="Old Default",
            model_id=m.id,
            scenario="sc1",
            is_default=True,
            is_active=True,
        )
        prof2 = AiModelProfile(
            code="prof-new-default",
            name="New Default",
            model_id=m.id,
            scenario="sc1",
            is_default=False,
            is_active=True,
        )
        self.session.add(prof1)
        self.session.add(prof2)
        self.session.commit()

        from app.modules.ai.model.ai import AiModelProfileUpdateRequest

        service = AiModelProfileService(self.session)
        service.update(AiModelProfileUpdateRequest(id=prof2.id, is_default=True))

        self.session.refresh(prof1)
        self.session.refresh(prof2)
        self.assertFalse(prof1.is_default)
        self.assertTrue(prof2.is_default)

    def test_model_partial_update_code_checks_uniqueness(self):
        from app.modules.ai.model.ai import AiModelUpdateRequest
        from app.modules.ai.service.model_service import AiModelService

        p = AiProvider(code="prov-uniq-test", name="P", adapter="openai-compatible", is_active=True)
        self.session.add(p)
        self.session.commit()
        m1 = AiModel(provider_id=p.id, code="code-1", name="M1", model_type="chat", is_active=True)
        m2 = AiModel(provider_id=p.id, code="code-2", name="M2", model_type="chat", is_active=True)
        self.session.add(m1)
        self.session.add(m2)
        self.session.commit()

        service = AiModelService(self.session)
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            service.update(AiModelUpdateRequest(id=m2.id, code="code-1"))
        self.assertEqual(ctx.exception.status_code, 409)

    # ------------------------------------------------------------------
    # 第一批止血回归（评审 2026-10-18 派修：AI-001/002/003/004/005）
    # ------------------------------------------------------------------

    def _seed_chat_runtime(self, *, pricing_config: str | None = None) -> tuple[AiProvider, AiModel, AiModelProfile]:
        """造一套可解析的 chat provider/model/profile 三件套并落库。"""
        provider = AiProvider(code="openai", name="OpenAI", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        model = AiModel(
            provider_id=provider.id,
            code="gpt-test",
            name="GPT Test",
            model_type="chat",
            pricing_config=pricing_config,
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        profile = AiModelProfile(
            code="default-chat", name="Default", model_id=model.id, scenario="default", is_default=True, is_active=True
        )
        self.session.add(profile)
        self.session.commit()
        return provider, model, profile

    def test_options_cannot_override_upstream_payload_fields(self):
        """AI-002：请求级 options 不得覆盖服务端构造的 payload 主字段（model/messages 等）。"""
        provider, model, profile = self._seed_chat_runtime()

        captured = {}

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                captured.update({"model": model, "messages": messages, "options": options})
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        service_messages = [{"role": "user", "content": "hi"}]
        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(
                    messages=service_messages,
                    options={
                        "model": "evil-model",
                        "messages": [{"role": "user", "content": "evil"}],
                        "temperature": 0.5,
                    },
                )
            )

        self.assertTrue(result["success"])
        self.assertEqual(captured["model"], model.code)
        self.assertEqual(captured["messages"], service_messages)
        self.assertNotIn("model", captured["options"])
        self.assertNotIn("messages", captured["options"])
        # 非保留字仍正常透传
        self.assertEqual(captured["options"]["temperature"], 0.5)

    def test_openai_http_stream_chat_carries_include_usage(self):
        """AI-003：OpenAI 兼容流式请求必须携带 stream_options.include_usage，最后一帧 usage 可计量。"""
        provider = AiProvider(code="bailian", name="百炼", adapter="bailian", api_key_cipher=encrypt_secret("sk"))
        adapter = BailianAdapter(provider)

        class FakeStreamResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter(
                    [
                        'data: {"choices":[{"delta":{"content":"hi"}}]}',
                        "",
                        'data: {"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}',
                        "",
                        "data: [DONE]",
                        "",
                    ]
                )

        with patch("httpx.stream", return_value=FakeStreamResponse()) as mock_stream:
            events = list(
                adapter.stream_chat(model="qwen-plus", messages=[{"role": "user", "content": "hi"}], options={})
            )

        payload = mock_stream.call_args.kwargs["json"]
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["stream_options"], {"include_usage": True})
        self.assertEqual(payload["model"], "qwen-plus")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hi"}])
        usage_event = next(e for e in events if e.get("usage"))
        self.assertEqual(usage_event["usage"]["totalTokens"], 3)

    def test_invalid_pricing_config_costs_zero_and_keeps_success(self):
        """AI-005：定价配置非法（如 "0.15元"）时按 0 计费，调用保持 success，不落入失败/降级路径。"""
        provider, model, profile = self._seed_chat_runtime(
            pricing_config='{"input_per_1m": "0.15元", "output_per_1m": "0.6元"}'
        )

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            result = AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}])
            )

        self.assertTrue(result["success"])
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.cost_micro_usd, 0)

    def test_soft_deleted_config_not_resolvable(self):
        """AI-001：软删除的 profile/model/provider 运行时解析一律视同不存在，不得继续计费。"""
        provider, model, profile = self._seed_chat_runtime()
        registry = AiModelRegistryService(self.session)
        now = datetime.now(UTC)

        # 基线：未删除时可解析
        resolved = registry.resolve(model_type="chat", scenario="default")
        self.assertEqual(resolved["profile"].id, profile.id)

        profile.delete_time = now
        self.session.add(profile)
        self.session.commit()
        with self.assertRaises(AiInvocationError) as ctx:
            registry.resolve(model_type="chat", scenario="default")
        self.assertEqual(ctx.exception.status_code, 404)

        profile.delete_time = None
        model.delete_time = now
        self.session.add(profile)
        self.session.add(model)
        self.session.commit()
        # 默认场景路径：join 直接过滤软删 model，404（配置已不存在）
        with self.assertRaises(AiInvocationError) as ctx:
            registry.resolve(model_type="chat", scenario="default")
        self.assertEqual(ctx.exception.status_code, 404)
        # profile_code 指定路径：profile 仍可查到，model 经 live_record 断言拦下，400
        with self.assertRaises(AiInvocationError) as ctx:
            registry.resolve(model_type="chat", profile_code=profile.code)
        self.assertEqual(ctx.exception.status_code, 400)

        model.delete_time = None
        provider.delete_time = now
        self.session.add(model)
        self.session.add(provider)
        self.session.commit()
        with self.assertRaises(AiInvocationError) as ctx:
            registry.resolve(model_type="chat", profile_code=profile.code)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_fallback_skips_soft_deleted_target(self):
        """AI-001：fallback 目标被软删除时不得降级到它（否则删除的配置仍会被调用并计费）。"""
        provider, model, profile = self._seed_chat_runtime()
        fb_provider = AiProvider(code="fb", name="FB", adapter="openai-compatible", is_active=True)
        self.session.add(fb_provider)
        self.session.commit()
        self.session.refresh(fb_provider)
        fb_model = AiModel(provider_id=fb_provider.id, code="fb-model", name="FB", model_type="chat", is_active=True)
        self.session.add(fb_model)
        self.session.commit()
        self.session.refresh(fb_model)
        fb_profile = AiModelProfile(
            code="fb-profile", name="FB Profile", model_id=fb_model.id, scenario="default", is_active=True
        )
        self.session.add(fb_profile)
        self.session.commit()
        profile.fallback_profile_id = fb_profile.id
        fb_profile.delete_time = datetime.now(UTC)
        self.session.add(profile)
        self.session.add(fb_profile)
        self.session.commit()

        called = {"fallback": False}

        class FailingAdapter:
            def chat(self, *, model, messages, options):
                raise RuntimeError("upstream down")

        class OkAdapter:
            def chat(self, *, model, messages, options):
                called["fallback"] = True
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        def fake_build(provider_obj):
            return FailingAdapter() if provider_obj.id == provider.id else OkAdapter()

        with patch("app.modules.ai.service.runtime_service.build_adapter", side_effect=lambda p: fake_build(p)):
            with self.assertRaises(AiInvocationError):
                AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertFalse(called["fallback"])

    def test_concurrent_keys_persisted_and_released_after_cancel(self):
        """AI-004：cc_keys 必须落库；worker 内存丢失（新会话）后 cancel 仍能从列恢复并精确 decr。"""
        from app.modules.base.service.cache_service import cache_get

        provider, model, profile = self._seed_chat_runtime()
        self.session.add(
            AiGovernanceRule(
                code="conc-cancel",
                name="Concurrent Cancel",
                scope_type="profile",
                profile_id=profile.id,
                period="day",
                max_concurrent=1,
                is_active=True,
            )
        )
        task = AiGenerationTask(task_type="chat", scenario="default", status="running", request_payload="{}")
        self.session.add(task)
        self.session.commit()

        from app.modules.ai.service.governance_service import AiGovernanceService

        governance = AiGovernanceService(self.session)
        invocation = governance.begin(user=None, provider=provider, model=model, profile=profile, task_id=task.id)

        # 核心回归：cc_keys 必须写进列（修复前只赋内存属性 _cc_keys，列永远为 None）
        self.assertIsNotNone(invocation.cc_keys)
        self.assertIn("ai:gov:cc:profile:", invocation.cc_keys)
        profile_key = f"ai:gov:cc:profile:{profile.id}"
        self.assertEqual(cache_get(profile_key), "1")

        # 模拟 worker 被 terminate：新会话重新加载（无内存属性），cancel 路径按列恢复并 decr
        with Session(self.engine) as fresh:
            fresh_task = fresh.get(AiGenerationTask, task.id)
            released = AiGovernanceService(fresh).release_for_generation_task(fresh_task)
            fresh.commit()
        self.assertEqual(released, 1)
        self.assertEqual(cache_get(profile_key), "0")

        with Session(self.engine) as verify:
            inv = verify.exec(select(AiRuntimeInvocation)).one()
            self.assertEqual(inv.status, "error")
            self.assertIsNone(inv.cc_keys)

    def test_adapter_input_error_does_not_trigger_fallback_or_retry(self):
        """AI-009：适配器参数错误（AdapterInputError）不降级不重试，直接 4xx，上游只被调一次。"""
        provider, model, profile = self._seed_chat_runtime()
        fb_provider = AiProvider(code="fb", name="FB", adapter="openai-compatible", is_active=True)
        self.session.add(fb_provider)
        self.session.commit()
        self.session.refresh(fb_provider)
        fb_model = AiModel(provider_id=fb_provider.id, code="fb-model", name="FB", model_type="chat", is_active=True)
        self.session.add(fb_model)
        self.session.commit()
        self.session.refresh(fb_model)
        fb_profile = AiModelProfile(
            code="fb-profile", name="FB Profile", model_id=fb_model.id, scenario="default", is_active=True
        )
        self.session.add(fb_profile)
        self.session.commit()
        profile.fallback_profile_id = fb_profile.id
        profile.retry_count = 2  # 即使配置了重试，参数错误也不得重试
        self.session.add(profile)
        self.session.commit()

        calls = {"failing": 0, "ok": 0}

        class FailingAdapter:
            def chat(self, *, model, messages, options):
                calls["failing"] += 1
                raise AdapterInputError("百炼 wan2.6 同步生图暂不支持 negative_prompt")

        class OkAdapter:
            def chat(self, *, model, messages, options):
                calls["ok"] += 1
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        with patch(
            "app.modules.ai.service.runtime_service.build_adapter",
            side_effect=lambda p: FailingAdapter() if p.id == provider.id else OkAdapter(),
        ):
            with self.assertRaises(AiInvocationError) as ctx:
                AiModelRuntimeService(self.session).chat(AiChatRequest(messages=[{"role": "user", "content": "hi"}]))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("negative_prompt", str(ctx.exception.detail))
        self.assertEqual(calls["failing"], 1)  # 重试未发生（否则 3 次）
        self.assertEqual(calls["ok"], 0)  # fallback 未触发（否则二次计费）

    def test_adapter_metadata_single_source_consistency(self):
        """AI-010：ADAPTERS 实现与 constants.AI_ADAPTERS 单一权威一致，队列与模型类型派生一致。"""
        self.assertEqual(set(ADAPTERS), set(AI_ADAPTERS))
        self.assertEqual(set(AI_TASK_QUEUES), {f"ai.{t}" for t in AI_MODEL_TYPES})

    def test_governance_metric_sums_single_query_values(self):
        """AI-019：_metric_sums 单次聚合三指标数值正确，且窗口外/其他 scope 的记录不计入。"""
        from app.modules.ai.service.governance_service import AiGovernanceService

        provider, model, profile = self._seed_chat_runtime()
        governance = AiGovernanceService(self.session)
        now = datetime.now(UTC)

        def add_log(**kw):
            self.session.add(
                AiModelCallLog(
                    provider_id=provider.id,
                    model_id=model.id,
                    profile_id=kw.get("profile_id", profile.id),
                    user_id=kw.get("user_id"),
                    scenario="default",
                    model_type="chat",
                    status="success",
                    total_tokens=kw.get("tokens", 0),
                    cost_micro_usd=kw.get("cost", 0),
                    created_at=kw.get("created_at", now),
                )
            )

        # 窗口内：2 次调用、300 token、500 micro-usd；窗口外 1 次；其他 profile 1 次
        add_log(tokens=100, cost=200)
        add_log(tokens=200, cost=300)
        add_log(tokens=999, cost=999, created_at=now - timedelta(days=2))
        other_profile = AiModelProfile(code="other-profile", name="Other", model_id=model.id, is_active=True)
        self.session.add(other_profile)
        self.session.commit()
        add_log(tokens=888, cost=888, profile_id=other_profile.id)
        self.session.commit()

        rule = AiGovernanceRule(
            code="metric-rule",
            name="Metric",
            scope_type="profile",
            profile_id=profile.id,
            period="day",
            max_requests=100,
            max_tokens=100_000,
            max_cost_micro_usd=1_000_000,
            is_active=True,
        )
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        count, tokens, cost = governance._metric_sums(rule, None, profile.id, start, end)
        self.assertEqual((count, tokens, cost), (2, 300, 500))

        # 空规则（三 limit 全 None）短路不查库，直接零值
        empty_rule = AiGovernanceRule(code="empty-rule", name="Empty", scope_type="global", period="day")
        self.assertEqual(governance._metric_sums(empty_rule, None, profile.id, start, end), (0, 0, 0))

    def test_profile_batch_decorate_matches_single(self):
        """AI-036：profile 批量装饰与单条装饰输出一致（page 场景消除 N+1）。"""
        from app.modules.ai.service.profile_service import AiModelProfileService

        provider, model, profile = self._seed_chat_runtime()
        service = AiModelProfileService(self.session)

        rows = service.list()
        target = next(r for r in rows if r["id"] == profile.id)
        self.assertEqual(target["modelName"], model.name)
        self.assertEqual(target["modelCode"], model.code)
        self.assertEqual(target["providerName"], provider.name)
        self.assertEqual(target["providerAdapter"], provider.adapter)
        # 批量与单条路径输出一致
        single = service.info(profile.id)
        self.assertEqual(single["modelName"], target["modelName"])
        self.assertEqual(single["providerName"], target["providerName"])

    def test_soft_delete_session_invariant_and_escape_hatch(self):
        """AI-034：Session 级软删不变量——所有 ORM SELECT 自动过滤，逃生口显式放行。"""
        from app.core.database import INCLUDE_DELETED_EXECUTION_OPTION

        provider, model, profile = self._seed_chat_runtime()
        now = datetime.now(UTC)
        profile.delete_time = now
        model.delete_time = now
        self.session.add(profile)
        self.session.add(model)
        self.session.commit()

        # 不变量：手写 select 也被自动过滤（不再依赖"记得写 where"）
        self.assertEqual(self.session.exec(select(AiModelProfile).where(AiModelProfile.id == profile.id)).first(), None)
        # get 路径：新会话（无 identity map 缓存）同样被过滤；同会话内存中已加载对象仍可访问（正确语义）
        with Session(self.engine) as fresh:
            self.assertEqual(fresh.get(AiModel, model.id), None)
            self.assertEqual(fresh.get(AiModelProfile, profile.id), None)

        # 逃生口：显式 execution option 放行（回收站/对账场景）
        visible = self.session.exec(
            select(AiModelProfile)
            .where(AiModelProfile.id == profile.id)
            .execution_options(**{INCLUDE_DELETED_EXECUTION_OPTION: True})
        ).first()
        self.assertIsNotNone(visible)
        self.assertIsNotNone(visible.delete_time)

    def test_call_log_records_task_id_for_generation_cost(self):
        """AI-030：异步生成任务调用日志落 task_id，任务维度成本可归集。"""
        provider, model, profile = self._seed_chat_runtime()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            AiModelRuntimeService(self.session).chat(
                AiChatRequest(messages=[{"role": "user", "content": "hi"}]), task_id=77
            )

        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.task_id, 77)

    def test_bootstrap_seeds_default_governance_rule_idempotent(self):
        """AI-027：bootstrap 幂等种入默认全局治理规则（observe 模式，不阻断调用）。"""
        from app.modules.ai import config as ai_config

        ai_config.bootstrap(self.session)
        ai_config.bootstrap(self.session)  # 幂等：重复调用不重复种

        from app.modules.ai.model.ai import AiGovernanceRule

        rules = self.session.exec(select(AiGovernanceRule).where(AiGovernanceRule.code == "default-global-daily")).all()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].mode, "observe")
        self.assertEqual(rules[0].scope_type, "global")
        self.assertTrue(rules[0].max_tokens and rules[0].max_cost_micro_usd)

    def test_ai_model_unique_constraint_rejects_duplicates(self):
        """AI-012：(provider_id, code, model_type) 库层唯一约束拦截并发导入重复。"""
        from sqlalchemy.exc import IntegrityError

        provider, model, profile = self._seed_chat_runtime()
        dup = AiModel(provider_id=provider.id, code=model.code, name="Dup", model_type=model.model_type)
        self.session.add(dup)
        with self.assertRaises(IntegrityError):
            self.session.exec(select(AiModel)).all()  # flush 触发约束
            self.session.commit()

    def test_ai_model_unique_index_ignores_soft_deleted_rows(self):
        """AI-012 修正：部分唯一索引只约束活跃行——软删后可重建同 code，活跃行仍互斥。"""
        from sqlalchemy.exc import IntegrityError

        provider, model, profile = self._seed_chat_runtime()
        model.delete_time = datetime.now(UTC)
        self.session.add(model)
        self.session.commit()

        # 软删行不占键：同 (provider, code, model_type) 可重新创建
        rebuilt = AiModel(provider_id=provider.id, code=model.code, name="Rebuilt", model_type=model.model_type)
        self.session.add(rebuilt)
        self.session.commit()
        self.assertIsNotNone(rebuilt.id)

        # 活跃行之间仍互斥
        self.session.add(AiModel(provider_id=provider.id, code=model.code, name="Dup2", model_type=model.model_type))
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_skip_masking_ignored_unless_globally_enabled(self):
        """AI-014：客户端传 skipMasking:true 不得关闭 PII 脱敏，仅在全局开关闭合时生效。"""
        provider, model, profile = self._seed_chat_runtime()

        class FakeAdapter:
            def chat(self, *, model, messages, options):
                return {
                    "content": "我的手机号是 13800138000",
                    "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2},
                }

        messages = [{"role": "user", "content": "hi"}]
        with patch("app.modules.ai.service.runtime_service.build_adapter", return_value=FakeAdapter()):
            # 默认全局开关关闭：skip_masking=True 被忽略，脱敏照常执行
            result = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=messages, skip_masking=True))
            self.assertNotIn("13800138000", result["content"])
            self.assertIn("138****8000", result["content"])

            # 全局开关闭合：才允许跳过脱敏（内部场景显式配置）
            with patch("app.modules.ai.service.runtime_service.settings.AI_ALLOW_SKIP_MASKING", True):
                result2 = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=messages, skip_masking=True))
            self.assertIn("13800138000", result2["content"])

            # 开关闭合但客户端未请求跳过：仍脱敏
            with patch("app.modules.ai.service.runtime_service.settings.AI_ALLOW_SKIP_MASKING", True):
                result3 = AiModelRuntimeService(self.session).chat(AiChatRequest(messages=messages))
            self.assertNotIn("13800138000", result3["content"])

    def test_retry_skips_non_retryable_status_and_uses_backoff(self):
        """AI-025：401/400 类非瞬态错误不重试直接抛；5xx 可重试。"""
        from app.modules.ai.service.adapters.base import UpstreamApiError
        from app.modules.ai.service.runtime_service import _is_retryable

        # 分类函数：HTTP 语义判定
        self.assertFalse(_is_retryable(UpstreamApiError("401", status_code=401)))
        self.assertFalse(_is_retryable(UpstreamApiError("400", status_code=400)))
        self.assertFalse(_is_retryable(UpstreamApiError("403 审核拒绝", status_code=403)))
        self.assertTrue(_is_retryable(UpstreamApiError("500", status_code=500)))
        self.assertTrue(_is_retryable(UpstreamApiError("429", status_code=429)))
        self.assertTrue(_is_retryable(UpstreamApiError("408", status_code=408)))
        self.assertTrue(_is_retryable(UpstreamApiError("连接超时")))  # 无 status_code = 网络层瞬态
        # P2：无状态码但属代码缺陷，重试结果相同
        self.assertFalse(_is_retryable(TypeError("unexpected keyword argument")))
        self.assertFalse(_is_retryable(KeyError("missing")))
        self.assertFalse(_is_retryable(AttributeError("no attribute")))

        provider, model, profile = self._seed_chat_runtime()
        profile.retry_count = 2
        profile.retry_delay_seconds = 0
        self.session.add(profile)
        self.session.commit()

        class UnauthorizedAdapter:
            def __init__(self):
                self.calls = 0

            def chat(self, *, model, messages, options):
                self.calls += 1
                raise UpstreamApiError("401 Unauthorized", status_code=401)

        class ServerErrorAdapter:
            def __init__(self):
                self.calls = 0

            def chat(self, *, model, messages, options):
                self.calls += 1
                if self.calls < 3:
                    raise UpstreamApiError("502 Bad Gateway", status_code=502)
                return {"content": "ok", "usage": {"promptTokens": 1, "completionTokens": 1, "totalTokens": 2}}

        service = AiModelRuntimeService(self.session)
        kwargs = {"messages": [{"role": "user", "content": "hi"}], "options": {}}

        unauthorized = UnauthorizedAdapter()
        with self.assertRaises(UpstreamApiError):
            service._invoke_with_retry(unauthorized, "chat", profile, model.code, kwargs)
        self.assertEqual(unauthorized.calls, 1)  # 401 不重试（否则 3 次）

        server_error = ServerErrorAdapter()
        result = service._invoke_with_retry(server_error, "chat", profile, model.code, kwargs)
        self.assertEqual(result["content"], "ok")
        self.assertEqual(server_error.calls, 3)  # 5xx 按配置重试至成功

    def test_retry_does_not_retry_defect_exceptions(self):
        """P2：无状态码的代码缺陷类异常不重试，避免一个 bug 被放大成 N 次上游调用与日志。"""
        _, model, profile = self._seed_chat_runtime()
        profile.retry_count = 3
        profile.retry_delay_seconds = 0
        self.session.add(profile)
        self.session.commit()

        class DefectAdapter:
            def __init__(self):
                self.calls = 0

            def chat(self, *, model, messages, options):
                self.calls += 1
                raise TypeError("chat() got an unexpected keyword argument 'foo'")

        adapter = DefectAdapter()
        with self.assertRaises(TypeError):
            AiModelRuntimeService(self.session)._invoke_with_retry(
                adapter,
                "chat",
                profile,
                model.code,
                {"messages": [{"role": "user", "content": "hi"}], "options": {}},
            )
        self.assertEqual(adapter.calls, 1)

    def test_options_reserved_keys_dropped_with_warning(self):
        """P2：保留键被丢弃时留痕，但只记键名（值可能是越权提示词）。"""
        from app.modules.ai.service.utils import _options_without_governance

        options = {"system": "你是一个越权提示词", "model": "gpt-x", "temperature": 0.2, "timeout": 30, "_trace": "t"}
        with self.assertLogs("app.modules.ai.service.utils", level="WARNING") as captured:
            filtered = _options_without_governance(options)

        self.assertEqual(filtered, {"temperature": 0.2})
        self.assertEqual(captured.records[0].dropped_option_keys, ["_trace", "model", "system"])
        self.assertNotIn("越权", captured.records[0].getMessage())

        # 无保留键时不告警，避免正常流量刷日志
        with patch("app.modules.ai.service.utils.logger") as mock_logger:
            _options_without_governance({"temperature": 0.2})
        mock_logger.warning.assert_not_called()

    def test_build_adapter_reuses_instances_for_same_config(self):
        """AI-017：同配置复用同一 adapter 实例（SDK client 随之复用），配置变更返回新实例。"""
        base = dict(code="pool-test", name="Pool", adapter="openai-compatible", is_active=True)
        p1 = AiProvider(base_url="https://api.a.com/v1", api_key_cipher=encrypt_secret("k1"), **base)
        a1 = build_adapter(p1)
        a2 = build_adapter(p1)
        self.assertIs(a1, a2)  # 同配置命中实例池

        p2 = AiProvider(base_url="https://api.a.com/v1", api_key_cipher=encrypt_secret("k2"), **base)
        a3 = build_adapter(p2)
        self.assertIsNot(a1, a3)  # 密钥变更 → 指纹变化 → 新实例

        p3 = AiProvider(base_url="https://api.b.com/v1", api_key_cipher=encrypt_secret("k1"), **base)
        a4 = build_adapter(p3)
        self.assertIsNot(a1, a4)  # baseUrl 变更同理

        with self.assertRaises(AdapterInputError):
            build_adapter(AiProvider(adapter="no-such-adapter", **{k: v for k, v in base.items() if k != "adapter"}))

    def test_adapter_timeout_yields_isolated_copy(self):
        """AI-017 并发修正：超时上下文产出副本，不改池化实例的 timeout/client。"""
        from app.modules.ai.service.utils import _adapter_timeout

        class _FakeAdapter:
            def __init__(self):
                self.timeout = 60

        pooled = _FakeAdapter()
        with _adapter_timeout(pooled, 300) as call_adapter:
            self.assertIsNot(call_adapter, pooled)
            self.assertEqual(call_adapter.timeout, 300)
        # 池中实例保持原值：并发请求不会互相覆盖超时
        self.assertEqual(pooled.timeout, 60)

        with _adapter_timeout(pooled, None) as same:
            self.assertIs(same, pooled)  # 未配置超时时零开销直接透传

    def test_stream_options_unsupported_detection(self):
        """AI-003 兜底判定：仅参数类 4xx + 报文点名该字段才算可降级。"""
        from app.modules.ai.service.adapters.base import UpstreamApiError, stream_options_unsupported

        self.assertTrue(
            stream_options_unsupported(
                UpstreamApiError("400 Bad Request: extra fields not permitted: stream_options", status_code=400)
            )
        )
        self.assertTrue(stream_options_unsupported(UpstreamApiError("422 invalid include_usage", status_code=422)))
        # 无关 400 不降级，否则"模型不存在"等真实错误会被掩盖成"少个 usage"
        self.assertFalse(stream_options_unsupported(UpstreamApiError("400 model not found", status_code=400)))
        # 5xx 走既有重试链，不在此处吞掉
        self.assertFalse(stream_options_unsupported(UpstreamApiError("500 stream_options", status_code=500)))
        self.assertFalse(stream_options_unsupported(RuntimeError("stream_options unsupported")))

    def test_openai_http_stream_falls_back_without_stream_options(self):
        """白名单网关 400 拒绝 stream_options 时去字段重试一次：正文不丢、不重复（AI-003 兜底）。"""
        from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter

        provider = AiProvider(
            code="whitelist-gw",
            name="白名单网关",
            adapter="openai-compatible",
            base_url="https://api.example.com/v1",
            api_key_cipher=encrypt_secret("sk"),
        )
        adapter = OpenAIHttpAdapter(provider)

        class RejectResponse:
            status_code = 400
            reason_phrase = "Bad Request"
            headers: dict = {}
            text = '{"error":{"message":"extra fields not permitted: stream_options"}}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def read(self):
                return b""

            def json(self):
                raise ValueError("not json")

            def raise_for_status(self):
                request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
                raise httpx.HTTPStatusError("400", request=request, response=self)

            def iter_lines(self):
                return iter([])

        class OkResponse:
            status_code = 200
            headers = {"x-request-id": "rid-2"}
            text = ""

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter(['data: {"choices":[{"delta":{"content":"hi"}}]}', "", "data: [DONE]", ""])

        # 用快照记录每次请求体：payload 在重试时被原地 pop，Mock 只存引用会两次都看到终态
        calls: list[dict] = []
        responses = [RejectResponse(), OkResponse()]

        def _fake_stream(method, url, **kwargs):
            calls.append(json.loads(json.dumps(kwargs["json"])))
            return responses[len(calls) - 1]

        with patch("httpx.stream", side_effect=_fake_stream):
            events = list(adapter.stream_chat(model="m", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(len(calls), 2)  # 只重试一次
        self.assertEqual(calls[0]["stream_options"], {"include_usage": True})
        self.assertNotIn("stream_options", calls[1])
        self.assertEqual([e["content"] for e in events if e["event"] == "delta"], ["hi"])

    def test_openai_compatible_stream_falls_back_without_stream_options(self):
        """SDK 路径同样兜底：首个 chunk 前抛 400 才重试，且不再携带 stream_options。"""
        from unittest.mock import Mock

        from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter

        provider = AiProvider(
            code="sdk-gw",
            name="SDK 网关",
            adapter="openai-compatible",
            base_url="https://gw.example.com/v1",
            api_key_cipher=encrypt_secret("sk"),
        )
        adapter = OpenAICompatibleAdapter(provider)

        class BadRequestError(Exception):
            status_code = 400

        class Chunk:
            def __init__(self, data: dict):
                self._data = data

            def model_dump(self, mode: str = "json"):
                return self._data

        seen: list[dict] = []

        def _create(**kwargs):
            seen.append(dict(kwargs))
            if len(seen) == 1:
                raise BadRequestError("Error code: 400 - Unrecognized request argument supplied: stream_options")
            return iter([Chunk({"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]})])

        adapter.client = Mock()
        adapter.client.chat.completions.create.side_effect = _create

        events = list(adapter.stream_chat(model="m", messages=[{"role": "user", "content": "hi"}], options={}))

        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["stream_options"], {"include_usage": True})
        self.assertNotIn("stream_options", seen[1])
        self.assertEqual([e["content"] for e in events if e["event"] == "delta"], ["hi"])

    def test_pooled_adapter_survives_detached_provider(self):
        """AI-017 池化回归：provider detached+expired 后复用池化 adapter 不抛 DetachedInstanceError。

        Session 默认 expire_on_commit=True：首次请求 commit + close 后实体过期且脱离，
        第二次同配置请求命中实例池。修复前 image() 日志路径访问 self.provider.adapter/.code
        即 DetachedInstanceError（生产第二次同配置生图必炸）；修复后初始化期物化。
        """
        from unittest.mock import Mock

        from sqlalchemy.orm.exc import DetachedInstanceError

        provider = AiProvider(code="pool-detach", name="PD", adapter="openai-compatible", is_active=True)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        a1 = build_adapter(provider)
        self.session.commit()  # expire_on_commit=True：provider 实体自此过期
        self.session.close()  # 请求结束：实体 detached + expired

        class _FakeImageResponse:
            def model_dump(self, mode: str = "json"):
                return {"data": [{"url": "https://img.example/a.png"}], "usage": None}

        with Session(self.engine) as fresh:
            p2 = fresh.exec(select(AiProvider).where(AiProvider.code == "pool-detach")).first()
            a2 = build_adapter(p2)
            self.assertIs(a1, a2)  # 同一库行同配置 → 命中实例池
            # 前提自证：旧实体确实 detached+expired（修复前日志路径就是这么炸的）
            with self.assertRaises(DetachedInstanceError):
                _ = a1.provider.adapter
            a1.client = Mock()
            a1.client.images.generate.return_value = _FakeImageResponse()
            result = a1.image(model="m", prompt="draw", options={})
        a1.client.images.generate.assert_called_once()
        self.assertEqual(result["data"][0]["url"], "https://img.example/a.png")
        self.assertEqual(a1.provider_code, "pool-detach")
        self.assertEqual(a1.adapter_code, "openai-compatible")

    def test_persistable_cc_keys_truncates_by_whole_key(self):
        """cc_keys 落库截断按整数个 key 进行：恒为合法 JSON（修复前字符串切 500 产生坏 JSON）。"""
        from app.modules.ai.service.governance_service import _CC_KEYS_MAX_LEN, _persistable_cc_keys

        keys = [f"ai:gov:cc:profile:{i}-aaaaaaaaaaaaaaaaaaaa" for i in range(30)]
        payload = _persistable_cc_keys(keys)
        self.assertLessEqual(len(payload), _CC_KEYS_MAX_LEN)
        decoded = json.loads(payload)  # 修复前：截断产物 json.loads 直接抛
        self.assertEqual(keys[: len(decoded)], decoded)  # 保留的是原列表前缀

        # 极端：单 key 就超限 → 空列表仍是合法 JSON
        self.assertEqual(json.loads(_persistable_cc_keys(["k" * 600])), [])

    def test_release_concurrent_tolerates_corrupt_persisted_keys(self):
        """_release_concurrent 对持久化坏 JSON（旧版截断遗留数据）容错跳过，cancel 路径不炸。"""
        from app.modules.ai.service.governance_service import AiGovernanceService

        provider, model, profile = self._seed_chat_runtime()
        invocation = AiRuntimeInvocation(
            invocation_id="inv-corrupt-cc-keys",
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            status="running",
            started_at=datetime.now(UTC),
            cc_keys='["ai:gov:cc:gl',  # 模拟旧版 [:500] 字符串截断产物
        )
        self.session.add(invocation)
        self.session.commit()

        AiGovernanceService(self.session)._release_concurrent(invocation)  # 修复前此处 json.loads 抛
        self.assertEqual(invocation._cc_keys, [])

    def test_bootstrap_revives_soft_deleted_rule(self):
        """AI-027 补漏：默认治理规则被软删后重启，bootstrap 复活种子而非撞 code 唯一键。

        修复前存在性检查被软删不变量过滤 → 误判不存在 → 插入同 code 行 →
        IntegrityError（MODULE_LOAD_STRICT 默认 True 时炸启动）。
        """
        from app.modules.ai import config as ai_config
        from app.modules.ai.service.utils import statement_including_deleted

        ai_config.bootstrap(self.session)
        rule = self.session.exec(select(AiGovernanceRule).where(AiGovernanceRule.code == "default-global-daily")).one()
        rule.delete_time = datetime.now(UTC)
        self.session.add(rule)
        self.session.commit()

        ai_config.bootstrap(self.session)  # 修复前此处 IntegrityError

        rows = self.session.exec(
            statement_including_deleted(select(AiGovernanceRule).where(AiGovernanceRule.code == "default-global-daily"))
        ).all()
        self.assertEqual(len(rows), 1)  # 复活而非新建
        self.assertIsNone(rows[0].delete_time)
        self.assertTrue(rows[0].is_active)


if __name__ == "__main__":
    unittest.main()
