"""凭据入库检测正则单测（设计 §9.3：高置信模式，warning 不阻断）。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_credential_detection.py -q
"""

from __future__ import annotations

import unittest

from app.modules.ai.service.security_service import detect_credential_patterns


class CredentialDetectionTestCase(unittest.TestCase):
    def test_openai_style_key_hit(self):
        text = "我的 key 是 sk-proj-abc123def456ghi789jkl 请妥善保管"
        self.assertIn("openai_style_key", detect_credential_patterns(text))

    def test_openai_style_key_short_miss(self):
        """sk- 后不足 20 字符不命中（避免截断片段误报）。"""
        self.assertEqual(detect_credential_patterns("sk-short"), [])

    def test_openai_style_word_boundary_miss(self):
        """英文单词内 sk- 不误伤（risk-value 的 sk 前无词边界）。"""
        self.assertEqual(detect_credential_patterns("a risk-value judgement sk-1"), [])

    def test_pem_private_key_hit(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA"
        self.assertIn("pem_private_key", detect_credential_patterns(text))

    def test_pem_generic_header_hit(self):
        text = "-----BEGIN PRIVATE KEY-----"
        self.assertIn("pem_private_key", detect_credential_patterns(text))

    def test_aws_access_key_hit(self):
        self.assertIn("aws_access_key", detect_credential_patterns("AKIAIOSFODNN7EXAMPLE"))

    def test_aws_access_key_miss(self):
        """非 AKIA 前缀 / 长度不足不命中。"""
        self.assertEqual(detect_credential_patterns("AKIA123"), [])
        self.assertEqual(detect_credential_patterns("BKIAIOSFODNN7EXAMPLE"), [])

    def test_credential_assignment_hit(self):
        for text in (
            "password=abc123def456ghij",
            "my api_key: abc123def456ghij",
            'config: "token": "eyJhbGciOiJIUzI1NiJ9"',
        ):
            self.assertIn("credential_assignment", detect_credential_patterns(text), text)

    def test_credential_assignment_short_value_miss(self):
        """值不足 16 字符不命中（短词不触发）。"""
        self.assertEqual(detect_credential_patterns("password=123456"), [])

    def test_chinese_business_text_no_false_positive(self):
        """中文业务文本（含 password 单词但非赋值形态）不误报。"""
        texts = (
            "客户的登录密码需要重置",
            "password 字段是必填的",
            "请设置强 password",
            "报价口径：8 折，含税",
        )
        for text in texts:
            self.assertEqual(detect_credential_patterns(text), [], text)

    def test_empty_text(self):
        self.assertEqual(detect_credential_patterns(""), [])
        self.assertEqual(detect_credential_patterns(None), [])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
