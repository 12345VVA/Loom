from __future__ import annotations

import os
import unittest
from pathlib import Path

from dotenv import dotenv_values
from helpers import make_test_engine  # noqa: E402
from sqlmodel import Session, SQLModel, select

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
    # D6 决策：缺 key 返回空串，由 setUp 统一 skipTest——恢复"本地默认全量绿"；
    # 配置 DEEPSEEK_API_KEY 后这些用例自动启用为真实外呼的 live 验证。
    return _env_value("DEEPSEEK_API_KEY")


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


_SSE_LINES = [
    'data: {"choices":[{"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"list_workflow_definitions","arguments":""}}]}}]}',
    "",
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]}}]}',
    "",
    'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
    "",
    'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}',
    "",
    "data: [DONE]",
    "",
]


class _FakeStreamResponse:
    is_error = False
    headers = {"x-request-id": "req-test-1"}

    def read(self):
        return None

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(_SSE_LINES)


class _FakeStreamCtx:
    def __enter__(self):
        return _FakeStreamResponse()

    def __exit__(self, *args):
        return False


class ToolCallAggregationTestCase(unittest.TestCase):
    """OpenAIHttpAdapter E1 流式 tool_calls 增量聚合。

    背景（真机走查实锤）：本通道此前未聚合——DeepSeek 等走本类的渠道，模型决定调
    工具时 done 帧无 toolCalls → agent 流式轮收到空正文且工具轮不执行（空回复落库）。
    与 openai_compatible 同构；[DONE] 帧不带 toolCalls 键（runtime 侧仅非 None 覆盖）。
    """

    def test_stream_aggregates_tool_calls_into_done_frame(self):
        from unittest.mock import patch

        from app.modules.ai.service.adapters import openai_http

        adapter = DeepSeekAdapter(_live_provider())
        with patch.object(openai_http.httpx, "stream", return_value=_FakeStreamCtx()):
            events = list(
                adapter.stream_chat(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": "q"}],
                    options={"max_tokens": 64, "temperature": 0.1},
                )
            )
        dones = [e for e in events if e.get("event") == "done"]
        with_tools = [e for e in dones if e.get("toolCalls")]
        self.assertTrue(with_tools)
        call = with_tools[0]["toolCalls"][0]
        self.assertEqual(call["id"], "call_1")
        self.assertEqual(call["function"]["name"], "list_workflow_definitions")
        self.assertEqual(call["function"]["arguments"], "{}")
        # [DONE] 帧（无 usage/finishReason）不带 toolCalls 键——runtime 仅非 None 覆盖
        done_frame = [e for e in dones if not e.get("usage") and not e.get("finishReason")]
        self.assertTrue(done_frame)
        self.assertNotIn("toolCalls", done_frame[0])
        # 全程无正文 delta（模型输出全为调用分片）
        self.assertFalse(any(e.get("event") == "delta" and e.get("content") for e in events))


class DeepSeekLiveTestCase(unittest.TestCase):
    def setUp(self):
        if not _deepseek_api_key():
            self.skipTest("缺 DEEPSEEK_API_KEY，DeepSeek live 用例跳过（配置后自动启用）")
        self.engine = make_test_engine()
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
            default_config='{"temperature": 0.1, "max_tokens": 1024}',
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
                options={"max_tokens": 1024, "temperature": 0.1},
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], model_code)
        self.assertTrue(str(result.get("content") or "").strip())
        log = self.session.exec(select(AiModelCallLog)).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.model_type, "chat")

    def test_live_deepseek_runtime_chat_json_schema_downgrades_to_json_object(self):
        """复现工作流 LLM 节点报错链路：json_schema 在 DeepSeek 会 400，须降级为 json_object。"""
        adapter = DeepSeekAdapter(_live_provider())
        model_code = _choose_model(adapter)
        profile = self._create_runtime_stack(model_code)

        result = AiModelRuntimeService(self.session).chat(
            AiChatRequest(
                profile_code=profile.code,
                messages=[
                    {
                        "role": "user",
                        "content": '请输出 JSON：{"question": "...", "answer": "..."}，'
                        '从这句话提取："世界上最高的山是什么？珠穆朗玛峰。"',
                    }
                ],
                options={"max_tokens": 128, "temperature": 0.1},
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "qa",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"},
                            },
                            "required": ["question", "answer"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
        )

        self.assertTrue(result["success"])
        import json

        parsed = json.loads(result["content"])
        self.assertIn("question", parsed)
        self.assertIn("answer", parsed)

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
                # 思考模型（v4 默认开启思维链）的 reasoning 增量也计入 max_tokens，预算须留足
                options={"max_tokens": 1024, "temperature": 0.1},
            )
        )

        self.assertTrue(events)
        self.assertTrue(any(item.get("event") == "delta" and item.get("content") for item in events))
        self.assertTrue(any(item.get("event") == "done" for item in events))
        self.assertTrue(any(item.get("usage") for item in events))


if __name__ == "__main__":
    unittest.main()
