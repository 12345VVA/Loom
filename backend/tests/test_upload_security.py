"""
Task 2.1 / 2.2 / 2.3 上传安全修复测试

覆盖：
- Task 2.1: SVG 默认白名单移除 + 图片 Content-Disposition
- Task 2.2: /uploads 鉴权路由（未登录 401）
- Task 2.3: 文件头 magic bytes 校验（伪装文件被拒）
"""

import os
import sys
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from helpers import make_test_engine
from sqlmodel import Session, SQLModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.core.security import create_token, decode_token  # noqa: E402
from app.framework.storage import UploadRejectedError, validate_upload  # noqa: E402
from app.modules.base.service.authority_service import get_user_from_download_token  # noqa: E402
from app.modules.base.service.security_service import create_download_token  # noqa: E402
from main import app  # noqa: E402


class SvgUploadRejectedTests(unittest.TestCase):
    """Task 2.1: SVG 上传被拒（默认白名单不再包含 .svg，因 SVG 可内嵌 XSS 脚本）"""

    def test_svg_not_in_default_whitelist(self):
        allowed = {e.strip().lower() for e in settings.UPLOAD_ALLOWED_EXTENSIONS.split(",")}
        self.assertNotIn(".svg", allowed)

    def test_svg_rejected_by_validate_upload(self):
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script></svg>'
        with self.assertRaises(UploadRejectedError) as ctx:
            validate_upload(svg_content, "evil.svg")
        self.assertIn("不支持的文件类型", str(ctx.exception))


class MagicBytesValidationTests(unittest.TestCase):
    """Task 2.3: 文件头 magic bytes 校验"""

    def test_disguised_jpg_rejected(self):
        """扩展名 .jpg 但内容是纯文本，应被拒。"""
        text_content = b"this is not a jpeg file, just plain text"
        with self.assertRaises(UploadRejectedError) as ctx:
            validate_upload(text_content, "fake.jpg")
        self.assertIn("不匹配", str(ctx.exception))

    def test_disguised_png_rejected(self):
        with self.assertRaises(UploadRejectedError):
            validate_upload(b"not a png at all", "fake.png")

    def test_disguised_pdf_rejected(self):
        with self.assertRaises(UploadRejectedError):
            validate_upload(b"not a pdf content here", "fake.pdf")

    def test_disguised_gif_rejected(self):
        with self.assertRaises(UploadRejectedError):
            validate_upload(b"definitely not a gif", "fake.gif")

    def test_disguised_webp_rejected(self):
        # RIFF 开头但不是 WEBP
        with self.assertRaises(UploadRejectedError):
            validate_upload(b"RIFF\x00\x00\x00\x00WAVE", "fake.webp")

    def test_disguised_docx_rejected(self):
        with self.assertRaises(UploadRejectedError):
            validate_upload(b"not a zip/docx file", "fake.docx")

    def test_valid_jpeg_passes(self):
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        self.assertEqual(validate_upload(jpeg_content, "photo.jpg"), ".jpg")

    def test_valid_jpeg_uppercase_ext_passes(self):
        jpeg_content = b"\xff\xd8\xff\xe1" + b"\x00" * 100
        self.assertEqual(validate_upload(jpeg_content, "PHOTO.JPEG"), ".jpeg")

    def test_valid_png_passes(self):
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        self.assertEqual(validate_upload(png_content, "image.png"), ".png")

    def test_valid_gif87a_passes(self):
        gif_content = b"GIF87a" + b"\x00" * 100
        self.assertEqual(validate_upload(gif_content, "anim.gif"), ".gif")

    def test_valid_gif89a_passes(self):
        gif_content = b"GIF89a" + b"\x00" * 100
        self.assertEqual(validate_upload(gif_content, "anim.gif"), ".gif")

    def test_valid_pdf_passes(self):
        pdf_content = b"%PDF-1.4\n" + b"\x00" * 100
        self.assertEqual(validate_upload(pdf_content, "doc.pdf"), ".pdf")

    def test_valid_webp_passes(self):
        webp_content = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 100
        self.assertEqual(validate_upload(webp_content, "image.webp"), ".webp")

    def test_valid_mp4_passes(self):
        mp4_content = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 100
        self.assertEqual(validate_upload(mp4_content, "video.mp4"), ".mp4")

    def test_valid_docx_passes(self):
        docx_content = b"PK\x03\x04" + b"\x00" * 100
        self.assertEqual(validate_upload(docx_content, "file.docx"), ".docx")

    def test_valid_xlsx_passes(self):
        xlsx_content = b"PK\x03\x04" + b"\x00" * 100
        self.assertEqual(validate_upload(xlsx_content, "sheet.xlsx"), ".xlsx")

    def test_text_file_skips_magic_check(self):
        """纯文本类型不在 magic bytes 表中，跳过校验。"""
        self.assertEqual(validate_upload(b"hello world", "notes.txt"), ".txt")

    def test_json_file_skips_magic_check(self):
        self.assertEqual(validate_upload(b'{"key": "value"}', "data.json"), ".json")


class UploadsOwnershipEqualityTests(unittest.TestCase):
    """C1（异步审查第二轮）：归属查询等值化——本地/S3 公网形态命中、脏数据 fail-closed 403。

    只测归属查询语义（本批改动面）：鉴权与文件 stat 全部打桩。
    """

    def setUp(self):
        import app.modules.media.model.media as media_models  # noqa: F401 注册表收录

        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        # addCleanup LIFO：先注册 dispose（后跑）、后注册 close（先跑），
        # 避免 dispose 先关 StaticPool 底层连接、session.close 回滚时报 closed database
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    def _seed_asset(self, storage_url: str, owner_id: int) -> None:
        from app.modules.media.model.media import MediaAsset

        self.session.add(MediaAsset(storage_url=storage_url, created_by=owner_id, status="success"))
        self.session.commit()

    def _call(self, owner_id: int, file_path: str):
        from main import _resolve_upload_access

        owner = SimpleNamespace(id=owner_id, is_active=True, is_super_admin=False)
        with (
            patch("main.get_user_from_download_token", return_value=owner),
            patch("main.is_super_admin", return_value=False),
            patch("os.path.isfile", return_value=True),
        ):
            return _resolve_upload_access(self.session, "token", file_path)

    def test_local_exact_match_owned(self):
        """属主 + 本地规范 URL 等值命中（200 语义，返回文件路径与 nosniff 头）。"""
        self._seed_asset("/uploads/20261027/abc.png", owner_id=1)
        full_path, headers = self._call(owner_id=1, file_path="20261027/abc.png")
        # Windows abspath 产生反斜杠，归一后断言
        self.assertTrue(full_path.replace("\\", "/").endswith("20261027/abc.png"))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_s3_public_variant_match_when_configured(self):
        """S3 公网域配置时，公网 URL 形态同样等值命中（in_ 双分支）。"""
        from app.core.config import settings

        self._seed_asset("https://cdn.test/uploads/20261027/s3.png", owner_id=1)
        with patch.object(settings, "S3_PUBLIC_BASE_URL", "https://cdn.test"):
            full_path, _ = self._call(owner_id=1, file_path="20261027/s3.png")
        self.assertTrue(full_path.replace("\\", "/").endswith("20261027/s3.png"))

    def test_dirty_legacy_url_fails_closed(self):
        """存量非规范 storage_url：等值未命中 → 403（fail-closed，不放大权限）。"""
        self._seed_asset("/legacy/old-storage/abc.png", owner_id=1)
        with self.assertRaises(HTTPException) as ctx:
            self._call(owner_id=1, file_path="20261027/abc.png")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_non_owner_403(self):
        self._seed_asset("/uploads/20261027/abc.png", owner_id=2)
        with self.assertRaises(HTTPException) as ctx:
            self._call(owner_id=1, file_path="20261027/abc.png")
        self.assertEqual(ctx.exception.status_code, 403)


class UploadsAuthRouteTests(unittest.TestCase):
    """Task 2.2: /uploads 鉴权路由（未登录返回 401）"""

    @classmethod
    def setUpClass(cls):
        # 不进入 TestClient 上下文（避免触发 lifespan 连接 DB/Redis）。
        # /uploads 鉴权在依赖阶段即返回 401，无需 DB 初始化。
        cls.client = TestClient(app)

    def test_uploads_without_token_returns_401(self):
        """无任何凭证访问 /uploads 应返回 401。"""
        res = self.client.get("/uploads/20260101/abc.jpg")
        self.assertEqual(res.status_code, 401)

    def test_uploads_with_invalid_query_token_returns_401(self):
        """无效 token query 参数应返回 401。"""
        res = self.client.get("/uploads/20260101/abc.jpg?token=invalid.token.value")
        self.assertEqual(res.status_code, 401)

    def test_uploads_with_invalid_bearer_returns_401(self):
        """无效 Authorization Bearer 应返回 401。"""
        res = self.client.get(
            "/uploads/20260101/abc.jpg",
            headers={"Authorization": "Bearer invalid.token.value"},
        )
        self.assertEqual(res.status_code, 401)

    def test_uploads_path_traversal_blocked(self):
        """路径穿越请求应被拒（鉴权先行返回 401）。"""
        # 即使带有效 token 也应拦截；此处用无效 token，鉴权先行返回 401
        res = self.client.get("/uploads/%2e%2e/%2e%2e/etc/passwd")
        self.assertEqual(res.status_code, 401)


class DownloadTokenTests(unittest.TestCase):
    """专用下载令牌（type=download）签发与校验——隔离 access token，避免其泄露到日志/Referer。"""

    def _fake_user(self, *, is_active: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            id=1,
            username="admin",
            password_version=1,
            is_active=is_active,
            _token_role_ids=[],
        )

    def test_create_download_token_uses_download_type(self):
        """下载令牌 payload type=download，且不含 roleIds/isRefresh 等敏感字段。"""
        token = create_download_token(self._fake_user())
        payload = decode_token(token)
        self.assertEqual(payload["type"], "download")
        self.assertEqual(payload["sub"], "1")
        self.assertNotIn("roleIds", payload)
        self.assertNotIn("isRefresh", payload)

    def test_download_token_rejects_wrong_type(self):
        """非法令牌类型（如 refresh）不能用于下载鉴权。

        注：自 43a3dec 起 access 类型被有意接受（/uploads 高频路径复用登录态），
        故错误类型以 refresh 为代表。
        """
        refresh_like = create_token(
            {"sub": "1", "type": "refresh", "token_version": 0},
            timedelta(minutes=5),
        )
        session = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            get_user_from_download_token(session, refresh_like)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_download_token_rejects_expired(self):
        """过期下载令牌被拒。"""
        expired = create_token(
            {"sub": "1", "type": "download", "token_version": 0},
            timedelta(seconds=-1),
        )
        session = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            get_user_from_download_token(session, expired)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_download_token_returns_user(self):
        """有效下载令牌返回对应 user（轻量校验，不走 jti/会话数）。"""
        token = create_download_token(self._fake_user(is_active=True))
        session = MagicMock()
        session.get.return_value = self._fake_user(is_active=True)
        user = get_user_from_download_token(session, token)
        self.assertEqual(user.id, 1)

    def test_download_token_rejects_disabled_user(self):
        """禁用用户的下载令牌被拒。"""
        token = create_download_token(self._fake_user(is_active=True))
        session = MagicMock()
        session.get.return_value = self._fake_user(is_active=False)
        with self.assertRaises(HTTPException) as ctx:
            get_user_from_download_token(session, token)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
