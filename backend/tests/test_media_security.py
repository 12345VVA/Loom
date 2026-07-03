"""
媒体服务安全修复测试（P0-12 / P0-13 / P0-14）。

覆盖：
1. DNS rebinding：mock DNS 解析返回内网 IP 被拒，且转存使用校验后的 IP URL 避免二次解析
2. 文件大小超限被拒（upload 流程早期校验）
3. 普通用户无法删除他人媒体
4. 普通用户 list 只看到自己的媒体
"""

from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.modules.base.model.auth import User
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import (
    MediaArtifact,
    MediaAssetService,
    _validate_remote_url,
)


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str):
        self.filename = filename
        self.file = BytesIO(content)
        self.content_type = content_type


def _make_user(user_id: int, *, is_super_admin: bool = False) -> User:
    return User(
        id=user_id,
        username=f"user{user_id}",
        full_name=f"user{user_id}",
        password_hash="x",
        is_active=True,
        is_super_admin=is_super_admin,
    )


class MediaSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    # ------------------------------------------------------------------
    # 1. DNS rebinding（P0-12）
    # ------------------------------------------------------------------
    def test_dns_rebinding_internal_ip_rejected(self):
        """DNS 解析返回内网 IP 时 _validate_remote_url 拒绝"""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 0))]):
            with self.assertRaises(ValueError) as ctx:
                _validate_remote_url("https://example.com/image.png")
        self.assertIn("内网", str(ctx.exception))

    def test_transfer_artifact_uses_ip_url_preventing_dns_rebinding(self):
        """转存时使用校验后的 IP URL + Host header，避免二次 DNS 解析导致 rebinding"""
        fake_response = MagicMock()
        fake_response.is_redirect = False
        fake_response.raise_for_status = Mock()
        fake_response.headers = {"content-type": "image/png"}
        fake_response.iter_bytes.return_value = [b"fake-image-data"]

        mock_stream = MagicMock()
        mock_stream.return_value.__enter__.return_value = fake_response
        mock_stream.return_value.__exit__.return_value = False

        storage = Mock()
        storage.save.return_value = "/uploads/safe.png"

        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            with patch("app.modules.media.service.media_service.safe_stream", mock_stream):
                with patch(
                    "app.modules.media.service.media_service.StorageService.get_instance",
                    return_value=storage,
                ):
                    service = MediaAssetService(self.session)
                    asset = MediaAsset(asset_type="image", source_type="ai_sync", status="transferring")
                    self.session.add(asset)
                    self.session.commit()
                    self.session.refresh(asset)
                    artifact = MediaArtifact(asset_type="image", original_url="https://example.com/image.png")
                    service._transfer_artifact(asset, artifact)

        # httpx 收到的 URL 应基于校验后的 IP，而非原 hostname
        call_args = mock_stream.call_args
        requested_url = call_args.args[1]
        request_headers = call_args.kwargs.get("headers")
        self.assertIn("93.184.216.34", requested_url)
        self.assertNotIn("example.com", requested_url)
        # Host header 保留原 hostname，确保目标服务器正确响应
        self.assertEqual(request_headers["Host"], "example.com")
        # 转存成功
        self.assertEqual(asset.status, "success")
        self.assertEqual(asset.storage_url, "/uploads/safe.png")

    # ------------------------------------------------------------------
    # 2. 文件大小超限（P0-13）
    # ------------------------------------------------------------------
    def test_upload_rejects_oversized_file(self):
        """upload 在读取文件后立即校验大小，超限返回 400"""
        large_content = b"x" * 100
        with patch.object(settings, "MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB", 0):
            with self.assertRaises(HTTPException) as ctx:
                MediaAssetService(self.session).upload(
                    FakeUploadFile("big.bin", large_content, "application/octet-stream")
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("超过", ctx.exception.detail)
        # 确认没有写入数据库
        from sqlmodel import select

        rows = list(self.session.exec(select(MediaAsset)).all())
        self.assertEqual(len(rows), 0)

    # ------------------------------------------------------------------
    # 3. 普通用户无法删除他人媒体（P0-14）
    # ------------------------------------------------------------------
    def test_non_super_admin_cannot_delete_others_media(self):
        """非超管用户删除他人媒体时返回 403，资产不被删除"""
        asset = MediaAsset(
            asset_type="image", source_type="upload", storage_url="/uploads/a.png", status="success",
            created_by=2,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        storage = Mock()
        storage.delete.return_value = True
        user = _make_user(1)

        with patch(
            "app.modules.media.service.media_service.StorageService.get_instance", return_value=storage
        ):
            with self.assertRaises(HTTPException) as ctx:
                MediaAssetService(self.session).delete([asset.id], current_user=user)

        self.assertEqual(ctx.exception.status_code, 403)
        storage.delete.assert_not_called()
        # 资产未被软删除
        self.assertIsNone(self.session.get(MediaAsset, asset.id).delete_time)

    def test_super_admin_can_delete_others_media(self):
        """超管用户可以删除任意用户的媒体"""
        asset = MediaAsset(
            asset_type="image", source_type="upload", storage_url="/uploads/a.png", status="success",
            created_by=2,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        storage = Mock()
        storage.delete.return_value = True
        admin = _make_user(1, is_super_admin=True)

        with patch(
            "app.modules.media.service.media_service.StorageService.get_instance", return_value=storage
        ):
            result = MediaAssetService(self.session).delete([asset.id], current_user=admin)

        self.assertTrue(result["success"])
        self.assertIsNotNone(self.session.get(MediaAsset, asset.id).delete_time)

    # ------------------------------------------------------------------
    # 4. 普通用户 list 只看到自己的媒体（P0-14）
    # ------------------------------------------------------------------
    def test_list_filters_to_own_media_for_non_super_admin(self):
        """非超管用户 list 仅返回自己创建的媒体"""
        self.session.add(
            MediaAsset(asset_type="image", source_type="upload", status="success", created_by=1)
        )
        self.session.add(
            MediaAsset(asset_type="video", source_type="upload", status="success", created_by=2)
        )
        self.session.add(
            MediaAsset(asset_type="audio", source_type="upload", status="success", created_by=1)
        )
        self.session.commit()

        user = _make_user(1)
        rows = MediaAssetService(self.session).list(query=None, current_user=user)

        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["createdBy"], 1)
        asset_types = {row["assetType"] for row in rows}
        self.assertEqual(asset_types, {"image", "audio"})

    def test_list_allows_super_admin_to_see_all(self):
        """超管用户 list 返回所有媒体"""
        self.session.add(
            MediaAsset(asset_type="image", source_type="upload", status="success", created_by=1)
        )
        self.session.add(
            MediaAsset(asset_type="video", source_type="upload", status="success", created_by=2)
        )
        self.session.commit()

        admin = _make_user(1, is_super_admin=True)
        rows = MediaAssetService(self.session).list(query=None, current_user=admin)

        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
