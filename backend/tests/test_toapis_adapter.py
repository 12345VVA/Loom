from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.modules.ai.model.ai import AI_ADAPTERS, AiProvider, AiProviderCreateRequest
from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.ai.service.adapters.factory import ADAPTERS, build_adapter
from app.modules.ai.service.adapters.toapis import (
    DEFAULT_TOAPIS_BASE_URL,
    DEFAULT_TOAPIS_UA,
    ToApisAdapter,
    _convert_pixel_size_to_ratio_and_resolution,
    _resolve_toapis_edition,
)


class TestToApisAdapter(unittest.TestCase):
    def setUp(self):
        self.provider = AiProvider(
            code="toapis",
            name="ToAPIs",
            adapter="toapis",
            base_url="https://api.toapis.cn",
            is_active=True,
        )

    def test_adapter_registration_and_validation(self):
        self.assertIn("toapis", AI_ADAPTERS)
        self.assertIn("toapis", ADAPTERS)
        req = AiProviderCreateRequest(
            code="toapis",
            name="ToAPIs",
            adapter="toapis",
            base_url="https://api.toapis.cn",
        )
        self.assertEqual(req.adapter, "toapis")

        adapter = build_adapter(self.provider)
        self.assertIsInstance(adapter, ToApisAdapter)
        self.assertEqual(adapter.default_base_url, DEFAULT_TOAPIS_BASE_URL)

    def test_headers_include_browser_user_agent(self):
        adapter = ToApisAdapter(self.provider)
        headers = adapter._headers()
        self.assertEqual(headers["User-Agent"], DEFAULT_TOAPIS_UA)

    def test_edition_resolution(self):
        self.assertEqual(_resolve_toapis_edition("gpt-image-2.5-flare"), "normal")
        self.assertEqual(_resolve_toapis_edition("gpt-image-2.5-flare-vip"), "vip")
        self.assertEqual(_resolve_toapis_edition("gpt-image-2.5-sunburst-official"), "official")

    def test_size_and_resolution_conversion(self):
        ratio, res = _convert_pixel_size_to_ratio_and_resolution("1024x1024")
        self.assertEqual(ratio, "1:1")
        self.assertEqual(res, "1K")

        ratio, res = _convert_pixel_size_to_ratio_and_resolution("1280x720")
        self.assertEqual(ratio, "16:9")

        ratio, res = _convert_pixel_size_to_ratio_and_resolution("720x1280")
        self.assertEqual(ratio, "9:16")

        ratio, res = _convert_pixel_size_to_ratio_and_resolution("16:9")
        self.assertEqual(ratio, "16:9")

    def test_normal_edition_image_generation(self):
        adapter = ToApisAdapter(self.provider)

        fake_submit_resp = MagicMock()
        fake_submit_resp.headers = {"x-request-id": "req-sub-1"}
        submit_data = {"id": "tsk_normal_1", "status": "pending"}

        fake_poll_resp = MagicMock()
        fake_poll_resp.headers = {"x-request-id": "req-poll-1"}
        poll_data = {
            "id": "tsk_normal_1",
            "status": "completed",
            "result": {"data": [{"url": "https://files.toapis.cn/gen_1.png"}]},
        }

        with (
            patch.object(adapter, "_post", return_value=(submit_data, fake_submit_resp)) as mock_post,
            patch.object(adapter, "_get", return_value=(poll_data, fake_poll_resp)) as mock_get,
        ):
            result = adapter.image(
                model="gpt-image-2.5-flare",
                prompt="小猫草地",
                options={
                    "size": "1024x1024",
                    "resolution": "2K",
                    "image": "https://example.com/ref.png",
                    "background": "transparent",
                },
            )

        mock_post.assert_called_once()
        path, payload = mock_post.call_args[0]
        self.assertEqual(path, "/v1/images/generations")
        self.assertEqual(payload["model"], "gpt-image-2.5-flare")
        self.assertEqual(payload["size"], "1:1")
        self.assertEqual(payload["resolution"], "2K")
        self.assertEqual(payload["background"], "transparent")
        self.assertEqual(payload["reference_images"], ["https://example.com/ref.png"])

        mock_get.assert_called_once_with("/v1/images/generations/tsk_normal_1")
        self.assertEqual(result["data"], [{"url": "https://files.toapis.cn/gen_1.png"}])
        self.assertEqual(result["requestId"], "tsk_normal_1")

    def test_official_edition_image_generation(self):
        adapter = ToApisAdapter(self.provider)

        fake_submit_resp = MagicMock()
        fake_submit_resp.headers = {"x-request-id": "req-sub-2"}
        submit_data = {"id": "tsk_off_1", "status": "pending"}

        fake_poll_resp = MagicMock()
        fake_poll_resp.headers = {"x-request-id": "req-poll-2"}
        poll_data = {
            "id": "tsk_off_1",
            "status": "completed",
            "result": {"data": [{"url": "https://files.toapis.cn/gen_off.png"}]},
            "usage": {"input_tokens": 50, "output_tokens": 200},
        }

        with (
            patch.object(adapter, "_post", return_value=(submit_data, fake_submit_resp)) as mock_post,
            patch.object(adapter, "_get", return_value=(poll_data, fake_poll_resp)),
        ):
            result = adapter.image(
                model="gpt-image-2.5-flare-official",
                prompt="水彩城堡",
                options={
                    "size": "1024x1024",
                    "quality": "low",
                    "image": "https://example.com/ref2.png",
                },
            )

        path, payload = mock_post.call_args[0]
        self.assertEqual(payload["model"], "gpt-image-2.5-flare-official")
        self.assertEqual(payload["size"], "1024x1024")
        self.assertEqual(payload["quality"], "low")
        self.assertEqual(payload["image_urls"], ["https://example.com/ref2.png"])

        self.assertEqual(result["data"], [{"url": "https://files.toapis.cn/gen_off.png"}])
        self.assertEqual(result["usage"]["promptTokens"], 50)
        self.assertEqual(result["usage"]["completionTokens"], 200)

    def test_vip_edition_image_to_image_multipart(self):
        adapter = ToApisAdapter(self.provider)

        fake_post_multipart = MagicMock(return_value=({"id": "tsk_vip_edit_1", "status": "pending"}, MagicMock()))
        fake_poll_resp = MagicMock()
        poll_data = {
            "id": "tsk_vip_edit_1",
            "status": "completed",
            "result": {"data": [{"url": "https://files.toapis.cn/gen_vip.png"}]},
            "usage": {"input_tokens": 40, "output_tokens": 150},
        }

        with (
            patch.object(adapter, "_post_vip_edits_multipart", fake_post_multipart),
            patch.object(adapter, "_get", return_value=(poll_data, fake_poll_resp)),
        ):
            result = adapter.image(
                model="gpt-image-2.5-flare-vip",
                prompt="小狐狸戴帽子",
                options={
                    "size": "1024x1024",
                    "quality": "low",
                    "image": "https://example.com/fox.png",
                },
            )

        fake_post_multipart.assert_called_once()
        kwargs = fake_post_multipart.call_args.kwargs
        self.assertEqual(kwargs["image_url"], "https://example.com/fox.png")
        self.assertEqual(kwargs["fields"]["model"], "gpt-image-2.5-flare-vip")
        self.assertEqual(kwargs["fields"]["quality"], "low")
        self.assertEqual(result["data"], [{"url": "https://files.toapis.cn/gen_vip.png"}])
        self.assertEqual(result["usage"]["promptTokens"], 40)
        self.assertEqual(result["usage"]["completionTokens"], 150)

    def test_polling_failure_raises_upstream_api_error(self):
        adapter = ToApisAdapter(self.provider)

        fake_submit_resp = MagicMock()
        submit_data = {"id": "tsk_fail_1", "status": "pending"}

        fake_poll_resp = MagicMock()
        poll_data = {
            "id": "tsk_fail_1",
            "status": "failed",
            "error": "Prompt contains sensitive content",
        }

        with (
            patch.object(adapter, "_post", return_value=(submit_data, fake_submit_resp)),
            patch.object(adapter, "_get", return_value=(poll_data, fake_poll_resp)),
        ):
            with self.assertRaises(UpstreamApiError) as ctx:
                adapter.image(model="gpt-image-2.5-flare", prompt="bad prompt", options={})

            self.assertIn("Prompt contains sensitive content", str(ctx.exception))

    def test_validate_toapis_remote_url_allowed_under_proxy_network(self):
        from app.framework.url_security import validate_remote_url

        # 模拟本地开启 Clash/TUN 模式，DNS 返回 198.18.x.x 代理网段 Fake-IP
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("198.18.0.88", 0))]):
            safe_url, hostname = validate_remote_url("https://files.toapis.cn/generated/1789973567_e25a8d56.png")

        self.assertEqual(hostname, "files.toapis.cn")
        self.assertIn("198.18.0.88", safe_url)


if __name__ == "__main__":
    unittest.main()
