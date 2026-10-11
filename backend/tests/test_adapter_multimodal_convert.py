"""多模态 IR → 厂商协议转换测试（WFI-2b，多模态一期阶段二）。

覆盖：
- Claude ``_to_claude_content``：text 透传、image_url 转 base64 source、
  system list content 防崩（extract_system_text）
- Gemini ``_gemini_content``：list 不再 str() 化、image_url 严格转 inlineData、
  空 parts 兜底
- ``media_fetch``：parse_data_uri 边界、extract_system_text 混合形态
"""

from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.ai.service.adapters.claude import ClaudeAdapter, _to_claude_content
from app.modules.ai.service.adapters.gemini import _gemini_content
from app.modules.ai.service.adapters.media_fetch import extract_system_text, parse_data_uri

IR = [
    {"type": "text", "text": "这张图里有什么？"},
    {"type": "image_url", "image_url": {"url": "https://example.com/photo.png"}},
]


class FakeResponse:
    headers = {"x-request-id": "req-1"}


def _claude_adapter() -> ClaudeAdapter:
    return ClaudeAdapter(AiProvider(code="anthropic", name="Anthropic", adapter="claude", is_active=True))


class ClaudeConvertTest(unittest.TestCase):
    def test_text_only_parts_pass_through(self) -> None:
        content = _to_claude_content([{"type": "text", "text": "你好"}])
        self.assertEqual(content, [{"type": "text", "text": "你好"}])

    def test_str_content_untouched(self) -> None:
        self.assertEqual(_to_claude_content("纯文本"), "纯文本")

    def test_image_url_converted_to_base64_source(self) -> None:
        raw = b"\x89PNG fake"
        b64 = base64.b64encode(raw).decode()
        data_uri = f"data:image/png;base64,{b64}"
        with (
            patch("app.modules.ai.service.adapters.claude.fetch_image_as_data_uri", return_value=data_uri),
        ):
            content = _to_claude_content(IR)
        self.assertEqual(content[0], {"type": "text", "text": "这张图里有什么？"})
        self.assertEqual(
            content[1],
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        )

    def test_image_fetch_failure_raises(self) -> None:
        with patch(
            "app.modules.ai.service.adapters.claude.fetch_image_as_data_uri",
            side_effect=UpstreamApiError("多模态图片下载失败"),
        ):
            with self.assertRaises(UpstreamApiError):
                _to_claude_content(IR)

    def test_chat_system_list_content_no_longer_type_error(self) -> None:
        """readiness #3 回归：system 为 list content 时不再 TypeError（防崩提取）。"""
        adapter = _claude_adapter()
        with patch.object(
            adapter,
            "_post",
            return_value=({"content": [{"type": "text", "text": "ok"}]}, FakeResponse()),
        ) as mocked_post:
            adapter.chat(
                model="claude-sonnet-4-5",
                messages=[
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": "sys-a"}, {"type": "text", "text": "sys-b"}],
                    },
                    {"role": "user", "content": "hi"},
                ],
                options={},
            )
        payload = mocked_post.call_args[0][1]
        self.assertEqual(payload["system"], "sys-a\nsys-b")

    def test_chat_user_multimodal_reaches_payload(self) -> None:
        raw = b"img"
        b64 = base64.b64encode(raw).decode()
        adapter = _claude_adapter()
        with patch(
            "app.modules.ai.service.adapters.claude.fetch_image_as_data_uri",
            return_value=f"data:image/png;base64,{b64}",
        ):
            with patch.object(
                adapter,
                "_post",
                return_value=({"content": [{"type": "text", "text": "ok"}]}, FakeResponse()),
            ) as mocked_post:
                adapter.chat(model="claude-sonnet-4-5", messages=[{"role": "user", "content": IR}], options={})
        payload = mocked_post.call_args[0][1]
        self.assertEqual(payload["messages"][0]["content"][1]["source"]["media_type"], "image/png")


class GeminiConvertTest(unittest.TestCase):
    def test_list_content_not_stringified(self) -> None:
        """readiness #4 回归：list 不再被 str() 化为 Python repr。"""
        with (
            patch(
                "app.modules.ai.service.adapters.gemini.fetch_image_as_data_uri",
                return_value="data:image/png;base64,QUJD",
            ),
        ):
            result = _gemini_content({"role": "user", "content": IR})
        self.assertEqual(result["role"], "user")
        self.assertEqual(result["parts"][0], {"text": "这张图里有什么？"})
        self.assertEqual(result["parts"][1], {"inlineData": {"mimeType": "image/png", "data": "QUJD"}})

    def test_str_content_unchanged(self) -> None:
        result = _gemini_content({"role": "user", "content": "普通"})
        self.assertEqual(result["parts"], [{"text": "普通"}])

    def test_empty_list_falls_back_to_blank_text(self) -> None:
        result = _gemini_content({"role": "user", "content": []})
        self.assertEqual(result["parts"], [{"text": ""}])

    def test_unknown_part_types_ignored(self) -> None:
        result = _gemini_content({"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": "x"}}, 42]})
        self.assertEqual(result["parts"], [{"text": ""}])

    def test_image_fetch_failure_raises(self) -> None:
        with patch(
            "app.modules.ai.service.adapters.gemini.fetch_image_as_data_uri",
            side_effect=UpstreamApiError("多模态图片下载失败"),
        ):
            with self.assertRaises(UpstreamApiError):
                _gemini_content({"role": "user", "content": IR})


class MediaFetchUtilTest(unittest.TestCase):
    def test_parse_data_uri_valid(self) -> None:
        b64 = base64.b64encode(b"abc").decode()
        mime, data = parse_data_uri(f"data:image/webp;base64,{b64}")
        self.assertEqual(mime, "image/webp")
        self.assertEqual(data, b64)

    def test_parse_data_uri_invalid(self) -> None:
        with self.assertRaises(UpstreamApiError):
            parse_data_uri("data:image/png;base64,!!!")
        with self.assertRaises(UpstreamApiError):
            parse_data_uri("not-a-data-uri")

    def test_extract_system_text_mixed(self) -> None:
        messages = [
            {"role": "system", "content": "sys-str"},
            {
                "role": "system",
                "content": [{"type": "text", "text": "sys-list"}, {"type": "image_url", "image_url": {}}],
            },
            {"role": "user", "content": [{"type": "text", "text": "ignored"}]},
        ]
        self.assertEqual(extract_system_text(messages), "sys-str\nsys-list")
        self.assertEqual(extract_system_text([]), "")
        self.assertEqual(
            extract_system_text([{"role": "system", "content": [{"type": "image_url", "image_url": {}}]}]),
            "",
        )


if __name__ == "__main__":
    unittest.main()
