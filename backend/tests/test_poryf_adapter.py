from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.core.config import settings
from app.modules.ai.model.ai import AI_ADAPTERS, AiProvider, AiProviderCreateRequest
from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.ai.service.adapters.factory import ADAPTERS, build_adapter
from app.modules.ai.service.adapters.poryf import (
    DEFAULT_PORYF_BASE_URL,
    PoryfAdapter,
    _is_own_backend_url,
)


def _make_provider(extra_config: dict | None = None) -> AiProvider:
    return AiProvider(
        code="poryf",
        name="Poryf",
        adapter="poryf",
        base_url="https://token.poryf.com/v1",
        is_active=True,
        extra_config=json.dumps(extra_config) if extra_config else None,
    )


class PoryfAdapterRegistrationTest(unittest.TestCase):
    def test_adapter_registration_and_validation(self):
        self.assertIn("poryf", AI_ADAPTERS)
        self.assertIn("poryf", ADAPTERS)
        req = AiProviderCreateRequest(
            code="poryf",
            name="Poryf（再来点Token）",
            adapter="poryf",
            base_url="https://token.poryf.com/v1",
        )
        self.assertEqual(req.adapter, "poryf")

        adapter = build_adapter(_make_provider())
        self.assertIsInstance(adapter, PoryfAdapter)
        self.assertEqual(adapter.default_base_url, DEFAULT_PORYF_BASE_URL)

    def test_default_timeout_is_300_and_extra_config_overrides(self):
        # 同步生图实测 21s~196s 波动，60s 默认必炸，适配器层默认必须放大到 300s
        self.assertEqual(PoryfAdapter(_make_provider()).timeout, 300.0)
        self.assertEqual(PoryfAdapter(_make_provider({"timeout": 600})).timeout, 600.0)

    def test_edit_reference_max_bytes_configurable(self):
        self.assertEqual(PoryfAdapter(_make_provider()).edit_reference_max_bytes, 1_048_576)
        self.assertEqual(
            PoryfAdapter(_make_provider({"edit_reference_max_bytes": 2048})).edit_reference_max_bytes, 2048
        )


class PoryfGenerationsTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PoryfAdapter(_make_provider())

    def test_text_to_image_payload_shape(self):
        fake_resp = MagicMock()
        fake_resp.headers = {"x-request-id": "poryf-req-1"}
        upstream = {
            "data": [{"b64_json": "fake-b64", "revised_prompt": ""}],
            "usage": {"input_tokens": 39, "output_tokens": 196, "total_tokens": 235},
        }

        with (
            patch.object(self.adapter, "_post", return_value=(upstream, fake_resp)) as mock_post,
        ):
            result = self.adapter.image(
                model="gpt-image-2.5-sunburst",
                prompt="橘猫晒太阳",
                options={
                    "size": "1024x1024",
                    "quality": "low",
                    # 以下应被拦截：response_format 多余（Poryf 默认回 b64），style 不支持
                    "response_format": "b64_json",
                    "style": "vivid",
                },
            )

        path, payload = mock_post.call_args[0]
        self.assertEqual(path, "/images/generations")
        self.assertEqual(
            payload,
            {"model": "gpt-image-2.5-sunburst", "prompt": "橘猫晒太阳", "size": "1024x1024", "quality": "low"},
        )
        # Poryf 实测响应只有 b64_json，透传给媒体层走 b64 落盘分支
        self.assertEqual(result["data"][0]["b64_json"], "fake-b64")
        self.assertEqual(result["requestId"], "poryf-req-1")
        # usage 别名归一：input_tokens -> promptTokens
        self.assertEqual(result["usage"]["promptTokens"], 39)
        self.assertEqual(result["usage"]["completionTokens"], 196)
        self.assertEqual(result["usage"]["totalTokens"], 235)

    def test_nonstandard_options_logged_and_dropped(self):
        with self.assertLogs("app.modules.ai.service.adapters.poryf", level="WARNING") as logs:
            with patch.object(self.adapter, "_post", return_value=({"data": []}, MagicMock())):
                self.adapter.image(
                    model="gpt-image-2.5-flare",
                    prompt="x",
                    options={"response_format": "url", "watermark": True},
                )
        self.assertTrue(any("已拦截非标准字段" in message for message in logs.output))

    def test_n_above_one_truncated_with_warning(self):
        with self.assertLogs("app.modules.ai.service.adapters.poryf", level="WARNING") as logs:
            with patch.object(self.adapter, "_post", return_value=({"data": []}, MagicMock())) as mock_post:
                self.adapter.image(model="gpt-image-2.5-flare", prompt="x", options={"n": 4})

        _, payload = mock_post.call_args[0]
        self.assertNotIn("n", payload)
        self.assertTrue(any("n=1" in message for message in logs.output))

    def test_invalid_quality_rejected_locally(self):
        with self.assertRaises(UpstreamApiError) as ctx:
            self.adapter.image(model="gpt-image-2.5-flare", prompt="x", options={"quality": "standard"})
        self.assertIn("画质参数非法", str(ctx.exception))

    def test_invalid_output_format_rejected_locally(self):
        with self.assertRaises(UpstreamApiError) as ctx:
            self.adapter.image(model="gpt-image-2.5-flare", prompt="x", options={"output_format": "webp"})
        self.assertIn("输出格式非法", str(ctx.exception))

    def test_upstream_error_maps_to_status_code(self):
        # Poryf 网关对 400/500 返回相同 error.type，错误判别必须依赖 HTTP 状态码
        request = httpx.Request("POST", "https://token.poryf.com/v1/images/generations")
        response = httpx.Response(
            500,
            request=request,
            json={"error": {"message": "internal service failure", "type": "bad_response_status_code"}},
        )
        with patch("app.modules.ai.service.adapters.poryf.httpx.post", return_value=response):
            with self.assertRaises(UpstreamApiError) as ctx:
                self.adapter._post_edits_multipart(fields={"model": "m"}, files={"image": ("a.png", b"x")})

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("internal service failure", str(ctx.exception))


class PoryfEditsTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PoryfAdapter(_make_provider())

    def _fake_upstream(self):
        fake_resp = MagicMock()
        fake_resp.headers = {"x-request-id": "poryf-req-edit"}
        return {
            "data": [{"b64_json": "edited-b64"}],
            "usage": {"input_tokens": 58, "output_tokens": 196, "total_tokens": 254},
        }, fake_resp

    def test_reference_image_routes_to_edits_multipart(self):
        upstream, fake_resp = self._fake_upstream()

        with (
            patch.object(
                self.adapter, "_load_reference_image", return_value=(b"fakepng", "ref.png", "image/png")
            ) as mock_load,
            patch.object(self.adapter, "_post_edits_multipart", return_value=(upstream, fake_resp)) as mock_multipart,
        ):
            result = self.adapter.image(
                model="gpt-image-2.5-sunburst",
                prompt="戴红色帽子",
                options={"image": "https://loom.example.com/uploads/ref.png", "size": "1024x1024", "quality": "low"},
            )

        mock_load.assert_called_once_with("https://loom.example.com/uploads/ref.png")
        kwargs = mock_multipart.call_args.kwargs
        self.assertEqual(
            kwargs["fields"],
            {"model": "gpt-image-2.5-sunburst", "prompt": "戴红色帽子", "size": "1024x1024", "quality": "low"},
        )
        self.assertEqual(kwargs["files"]["image"], ("ref.png", b"fakepng", "image/png"))
        self.assertEqual(result["data"][0]["b64_json"], "edited-b64")

    def test_multiple_reference_images_use_first_with_warning(self):
        upstream, fake_resp = self._fake_upstream()
        with (
            self.assertLogs("app.modules.ai.service.adapters.poryf", level="WARNING") as logs,
            patch.object(self.adapter, "_load_reference_image", return_value=(b"a", "a.png", "image/png")),
            patch.object(self.adapter, "_post_edits_multipart", return_value=(upstream, fake_resp)),
        ):
            self.adapter.image(
                model="gpt-image-2.5-flare",
                prompt="x",
                options={"image": ["https://a.example/1.png", "https://a.example/2.png"]},
            )
        self.assertTrue(any("单张参考图" in message for message in logs.output))

    def test_data_url_reference_decoded(self):
        b64 = base64.b64encode(b"tiny-image").decode()
        content, filename, mime = self.adapter._load_reference_image(f"data:image/png;base64,{b64}")
        self.assertEqual(content, b"tiny-image")
        self.assertEqual(filename, "reference.png")
        self.assertEqual(mime, "image/png")

    def test_oversize_reference_rejected_before_upstream(self):
        # 2.8MB 参考图实测会 500 且空跑 283s；超限必须在本地直接拒绝
        adapter = PoryfAdapter(_make_provider({"edit_reference_max_bytes": 8}))
        b64 = base64.b64encode(b"0123456789abcdef").decode()
        with self.assertRaises(UpstreamApiError) as ctx:
            adapter._load_reference_image(f"data:image/png;base64,{b64}")
        self.assertIn("超过上限", str(ctx.exception))

    def test_own_backend_url_skips_ssrf_and_goes_direct(self):
        with (
            patch.object(settings, "BACKEND_URL", "https://loom.example.com"),
            patch.object(self.adapter, "_download_direct", return_value=(b"own", "a.png", "image/png")) as mock_direct,
            patch.object(self.adapter, "_download_remote") as mock_remote,
        ):
            content, _, _ = self.adapter._load_reference_image("https://loom.example.com/uploads/a.png")

        self.assertEqual(content, b"own")
        mock_direct.assert_called_once()
        mock_remote.assert_not_called()

    def test_external_url_goes_through_ssrf_download(self):
        with (
            patch.object(self.adapter, "_download_remote", return_value=(b"ext", "b.png", "image/png")) as mock_remote,
            patch.object(self.adapter, "_download_direct") as mock_direct,
        ):
            content, _, _ = self.adapter._load_reference_image("https://cdn.example.com/b.png")

        self.assertEqual(content, b"ext")
        mock_remote.assert_called_once()
        mock_direct.assert_not_called()

    def test_is_own_backend_url_matches_configured_hosts(self):
        with patch.object(settings, "BACKEND_URL", "https://loom.example.com"):
            self.assertTrue(_is_own_backend_url("https://loom.example.com/uploads/a.png"))
            self.assertTrue(_is_own_backend_url("https://loom.example.com:443/uploads/a.png"))
            self.assertFalse(_is_own_backend_url("https://evil.example.com/uploads/a.png"))
            self.assertFalse(_is_own_backend_url("data:image/png;base64,xxx"))

    def test_empty_image_option_falls_back_to_generations(self):
        with patch.object(self.adapter, "_post", return_value=({"data": []}, MagicMock())) as mock_post:
            self.adapter.image(model="gpt-image-2.5-flare", prompt="x", options={"image": ""})

        path, _ = mock_post.call_args[0]
        self.assertEqual(path, "/images/generations")


if __name__ == "__main__":
    unittest.main()
