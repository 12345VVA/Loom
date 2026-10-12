"""媒体产物 TOS/S3 异步镜像测试（WFI-3b，多模态一期阶段三）。

覆盖：
- run：上传并回写 remote_url / 幂等跳过 / 失败不改资产状态（故障隔离红线）
- dispatch_media_mirror：开关关闭零派发；派发异常不影响主流程
- create_from_ai_result / retry 成功路径派发接线
"""

from __future__ import annotations

import base64
import unittest
from unittest.mock import Mock, patch

from helpers import make_test_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService
from app.modules.media.service.mirror_service import MediaMirrorService, dispatch_media_mirror

_PNG = base64.b64encode(b"mirror-png").decode()


def _result() -> dict:
    return {"provider": "volc", "model": "seedream", "data": [{"b64_json": _PNG, "mime_type": "image/png"}]}


class MediaMirrorTest(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage = Mock()
        self.storage.save.return_value = "/uploads/20261011/m.png"
        self.storage.read.return_value = b"mirror-png"
        self.session_factory = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _patch_storage(self):
        return patch(
            "app.modules.media.service.media_service.StorageService.get_instance",
            return_value=self.storage,
        )

    def _patch_session_local(self):
        return patch("app.core.database.SessionLocal", self.session_factory)

    def _make_asset(self, **overrides) -> MediaAsset:
        defaults = dict(
            asset_type="image",
            source_type="workflow",
            storage_url="/uploads/20261011/m.png",
            file_name="m.png",
            mime_type="image/png",
            status="success",
        )
        defaults.update(overrides)
        asset = MediaAsset(**defaults)
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def test_run_uploads_and_writes_remote_url(self):
        asset = self._make_asset()
        with (
            self._patch_session_local(),
            patch("app.framework.storage.StorageService.get_instance", return_value=self.storage),
            patch.object(
                MediaMirrorService, "upload_mirror_object", return_value="https://mirror.example.com/assets/a.png"
            ) as upload,
        ):
            result = MediaMirrorService().run(asset.id)
        self.assertEqual(result["remoteUrl"], "https://mirror.example.com/assets/a.png")
        upload.assert_called_once()
        self.assertEqual(upload.call_args[0][0], b"mirror-png")  # 本地字节经 StorageService 读回
        with Session(self.engine) as check:
            self.assertEqual(check.get(MediaAsset, asset.id).remote_url, "https://mirror.example.com/assets/a.png")

    def test_run_idempotent_skip_when_remote_url_exists(self):
        asset = self._make_asset(remote_url="https://mirror.example.com/exists.png")
        with self._patch_session_local():
            with patch.object(MediaMirrorService, "upload_mirror_object") as upload:
                result = MediaMirrorService().run(asset.id)
        self.assertTrue(result["skipped"])
        upload.assert_not_called()

    def test_run_skips_failed_or_missing_asset(self):
        with self._patch_session_local():
            self.assertEqual(MediaMirrorService().run(99999)["skipped"], True)
        failed = self._make_asset(status="failed", storage_url=None)
        with self._patch_session_local():
            self.assertEqual(MediaMirrorService().run(failed.id)["skipped"], True)

    def test_run_failure_does_not_touch_asset_status(self):
        """故障隔离红线：镜像失败向上抛（由 Celery 重试），资产状态不回退。"""
        asset = self._make_asset()
        with (
            self._patch_session_local(),
            patch("app.framework.storage.StorageService.get_instance", return_value=self.storage),
            patch.object(MediaMirrorService, "upload_mirror_object", side_effect=RuntimeError("TOS 不可达")),
        ):
            with self.assertRaises(RuntimeError):
                MediaMirrorService().run(asset.id)
        with Session(self.engine) as check:
            refreshed = check.get(MediaAsset, asset.id)
            self.assertEqual(refreshed.status, "success")
            self.assertIsNone(refreshed.remote_url)

    # ---------- 传输分派：TOS 原生 SDK / boto3 S3 兼容（2026-10-12 真机验证补充） ----------

    def test_endpoint_detection(self):
        from app.modules.media.service.mirror_service import _is_tos_native_endpoint

        self.assertTrue(_is_tos_native_endpoint("https://tos-cn-beijing.volces.com"))
        self.assertTrue(_is_tos_native_endpoint("tos-cn-shanghai.volces.com"))
        self.assertFalse(_is_tos_native_endpoint("https://tos-s3-cn-beijing.volces.com"))  # S3 兼容网关
        self.assertFalse(_is_tos_native_endpoint("https://minio.example.com"))
        self.assertFalse(_is_tos_native_endpoint(""))

    def test_tos_native_branch_sets_public_read_acl(self):
        """ark 自动桶场景：原生 SDK 上传 + 显式公共读 ACL（匿名可读是 remote_url 前提）。"""
        import tos

        with (
            patch.object(settings, "MEDIA_MIRROR_BUCKET", "b1"),
            patch.object(settings, "S3_ENDPOINT_URL", "https://tos-cn-beijing.volces.com"),
            patch.object(settings, "S3_ACCESS_KEY_ID", "ak"),
            patch.object(settings, "S3_SECRET_ACCESS_KEY", "sk"),
            patch.object(settings, "S3_REGION", "cn-beijing"),
            patch.object(settings, "MEDIA_MIRROR_PUBLIC_BASE_URL", ""),
            patch("tos.TosClientV2") as client_cls,
        ):
            url = MediaMirrorService().upload_mirror_object(b"png", "a.png", mime_type="image/png")
        client_cls.assert_called_once_with("ak", "sk", "tos-cn-beijing.volces.com", "cn-beijing")
        put = client_cls.return_value.put_object
        put.assert_called_once()
        self.assertEqual(put.call_args[0][0], "b1")
        self.assertTrue(put.call_args[0][1].startswith("assets/"))
        self.assertEqual(put.call_args[1]["content"], b"png")
        self.assertEqual(put.call_args[1]["acl"], tos.ACLType.ACL_Public_Read)
        self.assertEqual(put.call_args[1]["content_type"], "image/png")
        # 虚拟主机域名直链（native 端点形态）
        host = url.split("/")[2]
        self.assertEqual(host, "b1.tos-cn-beijing.volces.com")

    def test_s3_compat_branch_uses_boto3(self):
        with (
            patch.object(settings, "MEDIA_MIRROR_BUCKET", "b2"),
            patch.object(settings, "S3_ENDPOINT_URL", "https://tos-s3-cn-beijing.volces.com"),
            patch.object(settings, "MEDIA_MIRROR_PUBLIC_BASE_URL", ""),
            patch("boto3.client") as boto_client,
        ):
            url = MediaMirrorService().upload_mirror_object(b"png", "a.png", mime_type="image/png")
        boto_client.assert_called_once()
        put = boto_client.return_value.put_object
        put.assert_called_once()
        self.assertEqual(put.call_args[1]["Bucket"], "b2")
        self.assertEqual(put.call_args[1]["Body"], b"png")
        self.assertEqual(put.call_args[1]["ContentType"], "image/png")
        self.assertIn("b2.tos-s3-cn-beijing.volces.com", url)

    def test_dispatch_disabled_by_default(self):
        with patch("app.celery_app.celery_app.send_task") as send:
            with patch.object(settings, "MEDIA_MIRROR_ENABLED", False):
                dispatch_media_mirror(1)
        send.assert_not_called()

    def test_dispatch_sends_task_when_enabled(self):
        with patch("app.celery_app.celery_app.send_task") as send:
            with patch.object(settings, "MEDIA_MIRROR_ENABLED", True):
                dispatch_media_mirror(7)
        send.assert_called_once_with("media.mirror_asset", args=[7], queue="media.mirror")

    def test_dispatch_failure_swallowed(self):
        with patch("app.celery_app.celery_app.send_task", side_effect=ConnectionError("broker down")):
            with patch.object(settings, "MEDIA_MIRROR_ENABLED", True):
                dispatch_media_mirror(7)  # 不抛即通过

    def test_create_from_ai_result_dispatches_mirror(self):
        service = MediaAssetService(self.session)
        with (
            self._patch_storage(),
            self._patch_session_local(),
            patch("app.modules.media.service.media_service.dispatch_media_mirror") as dispatch,
            patch.object(settings, "MEDIA_MIRROR_ENABLED", True),
        ):
            assets = service.create_from_ai_result(
                task_type="image",
                result=_result(),
                request_payload={"prompt": "p"},
                source_type="workflow",
            )
        self.assertEqual(len(assets), 1)
        dispatch.assert_called_once()

    def test_retry_single_success_dispatches_mirror(self):
        asset = self._make_asset(status="failed", storage_url=None, original_url="https://x.volces.com/a.png")
        service = MediaAssetService(self.session)
        self.storage.read.return_value = b"bytes"
        with (
            patch(
                "app.modules.media.service.media_service._download_remote_file",
                return_value=(b"bytes", "image/png"),
            ),
            patch("app.modules.media.service.media_service.dispatch_media_mirror") as dispatch,
        ):
            service.retry_single(asset.id, current_user=None)
        dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
