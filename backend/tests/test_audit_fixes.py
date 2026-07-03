"""
审计修复测试

覆盖：
- Task A1: Content-Disposition 头注入修复（filename 含 \r\n、"、\\ 时被过滤）
- Task A3: 下载令牌验签不查 DB（verify_download_token 仅 JWT 验签 + Redis token_version）
- Task A5: 代码审查项（os._exit → sys.exit），无专门测试
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402
from app.modules.base.service.authority_service import (  # noqa: E402
    TOKEN_TYPE_DOWNLOAD,
    verify_download_token,
)


class ContentDispositionSanitizationTests(unittest.TestCase):
    """Task A1: Content-Disposition 头注入修复。"""

    def test_crlf_quote_and_backslash_are_replaced(self):
        """filename 含 \\r \\n " \\ 时，过滤后均被替换为下划线。"""
        malicious = 'evil\r\n"injected"\\path.pdf'
        safe = main._sanitize_download_filename(malicious)
        self.assertNotIn("\r", safe)
        self.assertNotIn("\n", safe)
        self.assertNotIn('"', safe)
        self.assertNotIn("\\", safe)

    def test_content_disposition_header_has_no_injection_chars(self):
        """组合后的 Content-Disposition 头不含任何注入字符。"""
        malicious = 'evil\r\n"inject".pdf'
        safe = main._sanitize_download_filename(malicious)
        cd = f'attachment; filename="{safe}"'
        # 头值中除 filename="..." 外层两个双引号外，不应再有双引号
        self.assertEqual(cd.count('"'), 2)
        # 不含换行符（防头分裂）
        self.assertNotIn("\r", cd)
        self.assertNotIn("\n", cd)
        # 不含反斜杠（防转义逃逸）
        self.assertNotIn("\\", cd)
        self.assertTrue(cd.startswith('attachment; filename="'))
        self.assertTrue(cd.endswith('"'))

    def test_normal_filename_preserved(self):
        """正常文件名应原样保留。"""
        self.assertEqual(main._sanitize_download_filename("report.pdf"), "report.pdf")
        self.assertEqual(main._sanitize_download_filename("2026-01-01_数据.pdf"), "2026-01-01_数据.pdf")

    def test_empty_filename_returns_empty(self):
        self.assertEqual(main._sanitize_download_filename(""), "")

    def test_only_special_chars_all_become_underscores(self):
        only = '""\r\n\\\\'
        safe = main._sanitize_download_filename(only)
        self.assertEqual(safe, "_" * len(only))


class VerifyDownloadTokenNoDbTests(unittest.TestCase):
    """Task A3: 下载令牌验签不查 DB。

    verify_download_token 仅依赖 JWT 验签 + Redis token_version，不需要 Session 参数。
    """

    def test_signature_does_not_require_session(self):
        """函数签名仅接受 token，不接受 DB Session。"""
        import inspect

        sig = inspect.signature(verify_download_token)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["token"])
        self.assertNotIn("session", params)

    def test_valid_token_passes_without_db(self):
        """合法下载令牌（type=download + token_version 匹配）应直接通过，无需 DB。"""
        with mock.patch(
            "app.modules.base.service.authority_service.decode_token",
            return_value={
                "sub": "1",
                "type": TOKEN_TYPE_DOWNLOAD,
                "token_version": 5,
                "jti": "abc",
            },
        ), mock.patch(
            "app.modules.base.service.authority_service.get_user_token_version",
            return_value=5,
        ) as tv_mock:
            payload = verify_download_token("fake.jwt.token")

        self.assertEqual(payload["sub"], "1")
        self.assertEqual(payload["type"], TOKEN_TYPE_DOWNLOAD)
        # token_version 来自 Redis 缓存路径，不应触发任何 DB 调用
        tv_mock.assert_called_once_with(1)

    def test_wrong_token_type_rejected(self):
        """type != download 应抛 401。"""
        from fastapi import HTTPException

        with mock.patch(
            "app.modules.base.service.authority_service.decode_token",
            return_value={"sub": "1", "type": "access", "token_version": 0},
        ):
            with self.assertRaises(HTTPException) as ctx:
                verify_download_token("fake.jwt.token")
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("类型", ctx.exception.detail)

    def test_missing_sub_rejected(self):
        """payload 缺 sub 应抛 401。"""
        from fastapi import HTTPException

        with mock.patch(
            "app.modules.base.service.authority_service.decode_token",
            return_value={"type": TOKEN_TYPE_DOWNLOAD, "token_version": 0},
        ):
            with self.assertRaises(HTTPException) as ctx:
                verify_download_token("fake.jwt.token")
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("用户标识", ctx.exception.detail)

    def test_stale_token_version_rejected(self):
        """令牌 token_version 低于当前 Redis 中的版本应抛 401（强制踢出/改密码生效）。"""
        from fastapi import HTTPException

        with mock.patch(
            "app.modules.base.service.authority_service.decode_token",
            return_value={
                "sub": "1",
                "type": TOKEN_TYPE_DOWNLOAD,
                "token_version": 3,
                "jti": "abc",
            },
        ), mock.patch(
            "app.modules.base.service.authority_service.get_user_token_version",
            return_value=4,
        ):
            with self.assertRaises(HTTPException) as ctx:
                verify_download_token("fake.jwt.token")
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("失效", ctx.exception.detail)

    def test_no_session_object_touched(self):
        """verify_download_token 内部不应触碰任何 Session/Query 对象。

        通过 mock sqlmodel.Session 确保未被实例化或调用。
        """
        with mock.patch(
            "app.modules.base.service.authority_service.decode_token",
            return_value={
                "sub": "42",
                "type": TOKEN_TYPE_DOWNLOAD,
                "token_version": 0,
            },
        ), mock.patch(
            "app.modules.base.service.authority_service.get_user_token_version",
            return_value=0,
        ), mock.patch("app.modules.base.service.authority_service.Session") as session_cls:
            verify_download_token("fake.jwt.token")
        session_cls.assert_not_called()


class DownloadTokenPayloadSlimTests(unittest.TestCase):
    """Task A3: 下载令牌 payload 去除冗余 userId 字段（只保留 sub）。"""

    def test_create_download_token_payload_has_no_user_id(self):
        """签发下载令牌时 payload 不含冗余 userId 字段。"""
        from app.modules.base.service.security_service import create_download_token

        captured = {}

        def fake_create_token(payload, delta):
            captured["payload"] = payload
            captured["delta"] = delta
            return "fake.token"

        user = mock.Mock(id=7, username="u")
        with mock.patch(
            "app.modules.base.service.security_service.get_user_token_version",
            return_value=1,
        ), mock.patch(
            "app.modules.base.service.security_service.create_token",
            side_effect=fake_create_token,
        ):
            token = create_download_token(user)

        self.assertEqual(token, "fake.token")
        payload = captured["payload"]
        self.assertIn("sub", payload)
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["type"], TOKEN_TYPE_DOWNLOAD)
        self.assertNotIn("userId", payload)
        self.assertIn("token_version", payload)
        self.assertIn("jti", payload)


if __name__ == "__main__":
    unittest.main()
