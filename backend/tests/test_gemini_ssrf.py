"""Gemini 适配器 SSRF 防护测试。

验证 _prepare_gemini_image_part 在下载远程图片时：
1. 拒绝内网 IP（10/8、172.16/12、192.168/16）
2. 拒绝云元数据服务 169.254.169.254
3. 拒绝回环地址 127.0.0.0/8、::1
4. 拒绝链路本地 169.254/16、fe80::/10
5. 拒绝 IPv6 本地地址 fc00::/7
6. 拒绝非 http/https 协议
7. 拒绝域名解析到内网 IP 的情况
8. 正常 https URL 通过校验
9. data: 内联图片不受影响
"""

from __future__ import annotations

import base64
import unittest
from unittest.mock import MagicMock, patch

from app.modules.ai.service.adapters.gemini import _prepare_gemini_image_part


class GeminiSSRFProtectionTests(unittest.TestCase):
    """Gemini 适配器 SSRF 防护测试。"""

    # ------------------------------------------------------------------
    # 内网 IP 直接出现在 URL 中
    # ------------------------------------------------------------------

    def test_rejects_private_ip_192_168(self):
        """192.168.0.0/16 私有段被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("192.168.1.1", 0))]):
            result = _prepare_gemini_image_part("http://192.168.1.1/img.png")
        self.assertIsNone(result)

    def test_rejects_private_ip_10(self):
        """10.0.0.0/8 私有段被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 0))]):
            result = _prepare_gemini_image_part("http://10.0.0.5/img.png")
        self.assertIsNone(result)

    def test_rejects_private_ip_172_16(self):
        """172.16.0.0/12 私有段被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("172.16.0.1", 0))]):
            result = _prepare_gemini_image_part("http://172.16.0.1/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 云元数据服务 / 链路本地
    # ------------------------------------------------------------------

    def test_rejects_metadata_service_169_254_169_254(self):
        """云元数据服务 169.254.169.254 被拒。"""
        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ):
            result = _prepare_gemini_image_part("http://169.254.169.254/latest/meta-data/")
        self.assertIsNone(result)

    def test_rejects_link_local_169_254(self):
        """169.254.0.0/16 链路本地段被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("169.254.1.1", 0))]):
            result = _prepare_gemini_image_part("http://169.254.1.1/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 回环地址
    # ------------------------------------------------------------------

    def test_rejects_loopback_127_0_0_1(self):
        """回环地址 127.0.0.1 被拒（早期检查，无需 mock DNS）。"""
        result = _prepare_gemini_image_part("http://127.0.0.1/img.png")
        self.assertIsNone(result)

    def test_rejects_loopback_ipv6(self):
        """IPv6 回环 ::1 被拒。"""
        result = _prepare_gemini_image_part("http://[::1]/img.png")
        self.assertIsNone(result)

    def test_rejects_localhost(self):
        """localhost 被拒。"""
        result = _prepare_gemini_image_part("http://localhost/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # IPv6 本地地址
    # ------------------------------------------------------------------

    def test_rejects_ipv6_unique_local_fc00(self):
        """IPv6 唯一本地地址 fc00::/7 被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("fc00::1", 0, 0, 0))]):
            result = _prepare_gemini_image_part("http://[fc00::1]/img.png")
        self.assertIsNone(result)

    def test_rejects_ipv6_link_local_fe80(self):
        """IPv6 链路本地地址 fe80::/10 被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("fe80::1", 0, 0, 0))]):
            result = _prepare_gemini_image_part("http://[fe80::1]/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 域名解析到内网 IP（DNS rebinding 防护）
    # ------------------------------------------------------------------

    def test_rejects_domain_resolving_to_private_ip(self):
        """域名解析到 192.168 内网 IP 被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("192.168.1.100", 0))]):
            result = _prepare_gemini_image_part("https://internal.example.com/img.png")
        self.assertIsNone(result)

    def test_rejects_domain_resolving_to_metadata_service(self):
        """域名解析到元数据服务 IP 被拒。"""
        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ):
            result = _prepare_gemini_image_part("https://metadata.example.com/img.png")
        self.assertIsNone(result)

    def test_rejects_domain_resolving_to_loopback(self):
        """域名解析到回环地址被拒。"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            result = _prepare_gemini_image_part("https://loopback.example.com/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 非法协议
    # ------------------------------------------------------------------

    def test_rejects_file_protocol(self):
        """file 协议被拒。"""
        result = _prepare_gemini_image_part("file:///etc/passwd")
        self.assertIsNone(result)

    def test_rejects_ftp_protocol(self):
        """ftp 协议被拒。"""
        result = _prepare_gemini_image_part("ftp://example.com/img.png")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 正常场景
    # ------------------------------------------------------------------

    def test_allows_normal_https_url(self):
        """正常 https URL 通过校验并下载图片。"""
        public_ip = "93.184.216.34"
        fake_image_data = b"fake-png-bytes"
        fake_b64 = base64.b64encode(fake_image_data).decode("utf-8")

        class FakeStreamResponse:
            headers = {"content-type": "image/png"}
            is_redirect = False

            def raise_for_status(self):
                pass

            def iter_bytes(self, chunk_size=8192):
                yield fake_image_data

        fake_response = FakeStreamResponse()
        mock_stream = MagicMock()
        mock_stream.return_value.__enter__.return_value = fake_response

        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, (public_ip, 0))]):
            with patch("app.modules.ai.service.adapters.gemini.safe_stream", mock_stream) as mocked_stream:
                result = _prepare_gemini_image_part("https://example.com/img.png")

        self.assertIsNotNone(result)
        self.assertEqual(result["inlineData"]["mimeType"], "image/png")
        self.assertEqual(result["inlineData"]["data"], fake_b64)

        # 校验 TOCTOU 防护：请求使用替换为 IP 的 safe_url，并附带原始 Host header
        call_args = mocked_stream.call_args
        self.assertEqual(call_args.args[0], "GET")
        self.assertIn(public_ip, call_args.args[1])
        # SNI 修复：原 hostname 作为第 3 参数传入 safe_stream，用于 TLS SNI/证书校验
        self.assertEqual(call_args.args[2], "example.com")
        self.assertEqual(call_args.kwargs["headers"]["Host"], "example.com")
        self.assertEqual(call_args.kwargs["follow_redirects"], False)

    def test_data_url_still_works(self):
        """data: 内联图片不受 SSRF 校验影响。"""
        result = _prepare_gemini_image_part("data:image/png;base64,iVBORw0KGgo=")
        self.assertIsNotNone(result)
        self.assertEqual(result["inlineData"]["mimeType"], "image/png")
        self.assertEqual(result["inlineData"]["data"], "iVBORw0KGgo=")

    def test_non_string_input_returns_none(self):
        """非字符串输入返回 None。"""
        self.assertIsNone(_prepare_gemini_image_part(None))
        self.assertIsNone(_prepare_gemini_image_part(123))


if __name__ == "__main__":
    unittest.main()
