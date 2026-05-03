from __future__ import annotations

import os
import unittest
from pathlib import Path

from dotenv import dotenv_values
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.secret import encrypt_secret
from app.modules.ai.model.ai import AiChatRequest, AiModel, AiModelCallLog, AiModelProfile, AiProvider
from app.modules.ai.service.adapters.factory import DeepSeekAdapter
from app.modules.ai.service.ai_service import AiModelRuntimeService


def _env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value.strip()
    env_path = Path(__file__).resolve().parents[1] / ".env"
    return str(dotenv_values(env_path).get(name) or "").strip()


def _deepseek_api_key() -> str:
    key = _env_value("DEEPSEEK_API_KEY")
    if not key:
        raise AssertionError("backend/.env 必须配置 DEEPSEEK_API_KEY，DeepSeek live 测试不再跳过")
    return key


def _live_provider() -> AiProvider:
    base_url = _env_value("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    return AiProvider(
        code="deepseek",
        name="DeepSeek Live",
        adapter="deepseek",
        base_url=base_url,
        api_key_cipher=encrypt_secret(_deepseek_api_key()),
        is_active=True,
    )


def _choose_model(adapter: DeepSeekAdapter) -> str:
    preferred = _env_value("DEEPSEEK_MODEL")
    data, _ = adapter._get(adapter.models_path)
    model_ids = [item.get("id") for item in data.get("data", []) if item.get("id")]
    if not model_ids:
        raise AssertionError("DeepSeek /models 未返回可用模型")
    if preferred:
        if preferred not in model_ids:
            raise AssertionError(f"DEEPSEEK_MODEL={preferred} 不在 DeepSeek /models 返回列表中")
        return preferred
    for candidate in ("deepseek-chat", "deepseek-v4-flash", "deepseek-reasoner", "deepseek-v4-pro"):
        if candidate in model_ids:
            return candidate
    return model_ids[0]


def _parse_sse_chunks(chunks: list[str]) -> list[dict]:
    import json

    events = []
    for part in "".join(chunks).split("\n\n"):
        part = part.strip()
        if part.startswith("data:"):
            events.append(json.loads(part[5:].strip()))
    return events


class DeepSeekLiveTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _create_runtime_stack(self, model_code: str) -> AiModelProfile:
        provider = _live_provider()
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)

        model = AiModel(
            provider_id=provider.id,
            code=model_code,
            name=f"DeepSeek Live {model_code}",
            model_type="chat",
            default_config='{"temperature": 0.1, "max_tokens": 64}',
            is_active=True,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)

        profile = AiModelProfile(
            code="deepseek-live",
            name="DeepSeek Live",
            model_id=model.id,
            scenario="default",
            is_default=True,
            is_active=True,
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def test_live_deepseek_provider_models_endpoint(self):
        adapter = DeepSeekAdapter(_live_provider())

        result = adapter.test()

        self.assertTrue(result["success"])
        self.assertGreater(result["count"], 0)

    def test_live_deepseek_runtime_chat_and_call_log(self):
        adapter = DeepSeekAdapter(_live_provider())
        model_code = _choose_model(adapter)
        profile = self._create_runtime_stack(model_code)

        result = AiModelRuntimeService(self.session).chat(
            AiChatRequest(
                profile_code=profile.code,
                messages=[
                    {
                        "role": "user",
                        "content": "请只回复四个汉字：测试成功",
                    }
                ],
                options={"max_tokens": 32, "temperature": 0.1},
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], model_code)
        self.assertTrue(str(result.get("content") or "").strip())
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.model_type, "chat")

    def test_live_deepseek_adapter_stream_chat(self):
        adapter = DeepSeekAdapter(_live_provider())
        model_code = _choose_model(adapter)

        events = list(
            adapter.stream_chat(
                model=model_code,
                messages=[
                    {
                        "role": "user",
                        "content": "请用一句很短的话确认流式输出可用。",
                    }
                ],
                options={"max_tokens": 64, "temperature": 0.1},
            )
        )

        self.assertTrue(events)
        self.assertTrue(any(item.get("event") == "done" for item in events))
        self.assertTrue(any(item.get("usage") for item in events))


if __name__ == "__main__":
    unittest.main()
