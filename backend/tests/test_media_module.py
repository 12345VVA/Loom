from __future__ import annotations

import base64
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.ai.controller.aiapi.model import AiRuntimeController, _run_sync_image_pipeline
from app.modules.ai.model.ai import AiGenerationTask, AiImageRequest
from app.modules.base.model.auth import User
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService, _validate_remote_url


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str):
        from io import BytesIO

        self.filename = filename
        self.file = BytesIO(content)
        self.content_type = content_type


class MediaModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_upload_creates_media_asset(self):
        storage = Mock()
        storage.upload.return_value = "/uploads/20260503/a.png"

        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            result = MediaAssetService(self.session).upload(FakeUploadFile("a.png", b"image", "image/png"))

        asset = self.session.get(MediaAsset, result["id"])
        self.assertEqual(asset.asset_type, "image")
        self.assertEqual(asset.source_type, "upload")
        self.assertEqual(asset.storage_url, "/uploads/20260503/a.png")
        self.assertEqual(asset.md5, hashlib.md5(b"image").hexdigest())
        self.assertEqual(asset.status, "success")

    def test_ai_task_base64_result_creates_success_asset(self):
        payload = base64.b64encode(b"png-bytes").decode()
        task = AiGenerationTask(
            task_type="image",
            scenario="default",
            profile_code="volc-image",
            status="success",
            request_payload=json.dumps({"prompt": "draw", "options": {"size": "2560x1440"}}),
            result_payload=json.dumps(
                {
                    "provider": "volcengine-ark",
                    "model": "doubao-seedream",
                    "profile": "volc-image",
                    "data": [{"b64_json": payload, "mime_type": "image/png"}],
                }
            ),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        storage = Mock()
        storage.save.return_value = "/uploads/20260503/generated.png"
        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            assets = MediaAssetService(self.session).create_from_ai_task(task)

        self.assertEqual(len(assets), 1)
        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.status, "success")
        self.assertEqual(asset.asset_type, "image")
        self.assertEqual(asset.source_task_id, task.id)
        self.assertEqual(asset.storage_url, "/uploads/20260503/generated.png")
        self.assertEqual(asset.md5, hashlib.md5(b"png-bytes").hexdigest())
        self.assertEqual(asset.provider_code, "volcengine-ark")
        self.assertEqual(asset.model_code, "doubao-seedream")
        self.assertEqual(asset.prompt, "draw")

    def test_ai_task_transfer_failure_marks_asset_failed_but_task_success(self):
        task = AiGenerationTask(
            task_type="image",
            status="success",
            request_payload=json.dumps({"prompt": "draw"}),
            result_payload=json.dumps({"data": [{"url": "http://127.0.0.1/a.png"}]}),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        assets = MediaAssetService(self.session).create_from_ai_task(task)

        self.assertEqual(self.session.get(AiGenerationTask, task.id).status, "success")
        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.status, "failed")
        self.assertIn("本地地址", asset.error_message)

    def test_delete_soft_deletes_asset_and_calls_storage_delete(self):
        asset = MediaAsset(asset_type="image", source_type="upload", storage_url="/uploads/a.png", status="success")
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        storage = Mock()
        storage.delete.return_value = True
        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            result = MediaAssetService(self.session).delete([asset.id])

        self.assertTrue(result["storageDeleteResults"][asset.id])
        storage.delete.assert_called_once_with("/uploads/a.png")
        self.assertIsNotNone(self.session.get(MediaAsset, asset.id).delete_time)

    def test_delete_keeps_asset_when_storage_delete_returns_false(self):
        asset = MediaAsset(asset_type="image", source_type="upload", storage_url="/uploads/a.png", status="success")
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        storage = Mock()
        storage.delete.return_value = False
        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            result = MediaAssetService(self.session).delete([asset.id])

        asset = self.session.get(MediaAsset, asset.id)
        self.assertFalse(result["success"])
        self.assertEqual(result["failedIds"], [asset.id])
        self.assertIsNone(asset.delete_time)
        self.assertEqual(asset.status, "success")
        self.assertIn("删除失败", asset.error_message)

    def test_stats_filters_to_current_user_for_non_admin(self):
        self.session.add(MediaAsset(asset_type="image", source_type="upload", status="success", created_by=1))
        self.session.add(MediaAsset(asset_type="video", source_type="upload", status="success", created_by=2))
        self.session.commit()

        stats = MediaAssetService(self.session).stats(
            User(id=1, username="u1", full_name="u1", password_hash="x", is_active=True)
        )

        self.assertEqual(stats["typeCounts"], {"image": 1})

    def test_stats_allows_super_admin_to_see_all(self):
        self.session.add(MediaAsset(asset_type="image", source_type="upload", status="success", created_by=1))
        self.session.add(MediaAsset(asset_type="video", source_type="upload", status="success", created_by=2))
        self.session.commit()

        stats = MediaAssetService(self.session).stats(
            User(id=1, username="admin", full_name="admin", password_hash="x", is_active=True, is_super_admin=True)
        )

        self.assertEqual(stats["typeCounts"], {"image": 1, "video": 1})

    def test_create_from_ai_result_uses_ai_sync_source(self):
        payload = base64.b64encode(b"sync-png").decode()
        storage = Mock()
        storage.save.return_value = "/uploads/20260503/sync.png"

        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            assets = MediaAssetService(self.session).create_from_ai_result(
                task_type="image",
                result={
                    "provider": "volc",
                    "model": "seedream",
                    "data": [{"b64_json": payload, "mime_type": "image/png"}],
                },
                request_payload={"prompt": "draw", "options": {}},
                source_type="ai_sync",
                created_by=1,
                profile_code="image-profile",
            )

        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.source_type, "ai_sync")
        self.assertIsNone(asset.source_task_id)
        self.assertEqual(asset.created_by, 1)
        self.assertEqual(asset.status, "success")

    def test_create_from_ai_result_deduplicates_same_source_and_md5(self):
        payload = base64.b64encode(b"sync-png").decode()
        storage = Mock()
        storage.save.return_value = "/uploads/20260503/sync.png"
        service = MediaAssetService(self.session)

        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            first = service.create_from_ai_result(
                task_type="image",
                result={"data": [{"b64_json": payload, "mime_type": "image/png"}]},
                request_payload={"prompt": "draw"},
                source_type="ai_sync",
                created_by=1,
            )
            second = service.create_from_ai_result(
                task_type="image",
                result={"data": [{"b64_json": payload, "mime_type": "image/png"}]},
                request_payload={"prompt": "draw again"},
                source_type="ai_sync",
                created_by=1,
            )

        rows = list(self.session.exec(select(MediaAsset).where(MediaAsset.delete_time == None)).all())  # noqa: E711
        self.assertEqual(len(rows), 1)
        self.assertEqual(first[0].id, rows[0].id)
        self.assertNotEqual(second[0].id, rows[0].id)
        storage.save.assert_called_once()

    def test_sync_image_controller_ignores_media_persist_failure(self):
        controller = AiRuntimeController()
        payload = AiImageRequest(profile_code="image-profile", prompt="draw")
        expected = {"success": True, "data": [{"url": "https://example.com/a.png"}]}

        with patch("app.modules.ai.controller.aiapi.model.run_in_threadpool", side_effect=lambda func: func()):
            with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as runtime_cls:
                runtime_cls.return_value.image.return_value = expected
                with patch("app.modules.ai.controller.aiapi.model.MediaAssetService") as media_cls:
                    media_cls.return_value.create_from_ai_result.side_effect = RuntimeError("persist failed")
                    with patch("app.modules.ai.controller.aiapi.model.logger") as logger_mock:
                        import asyncio

                        result = asyncio.run(
                            controller.image(
                                payload,
                                User(id=1, username="u1", full_name="u1", password_hash="x", is_active=True),
                                self.session,
                            )
                        )

        self.assertEqual(result, expected)
        logger_mock.error.assert_called()

    def test_sync_image_controller_uses_threadpool_wrapper(self):
        controller = AiRuntimeController()
        payload = AiImageRequest(profile_code="image-profile", prompt="draw")
        expected = {"success": True, "data": [{"url": "https://example.com/a.png"}]}

        def fake_run_in_threadpool(func):
            self.assertEqual(func.keywords["payload"].profile_code, "image-profile")
            return expected

        with patch(
            "app.modules.ai.controller.aiapi.model.run_in_threadpool", side_effect=fake_run_in_threadpool
        ) as mocked:
            import asyncio

            result = asyncio.run(
                controller.image(
                    payload,
                    User(id=1, username="u1", full_name="u1", password_hash="x", is_active=True),
                    self.session,
                )
            )

        self.assertEqual(result, expected)
        self.assertTrue(mocked.called)

    def test_run_sync_image_pipeline_uses_fresh_session_and_persists_media(self):
        payload = AiImageRequest(profile_code="image-profile", prompt="draw")
        user = User(username="u1", full_name="u1", password_hash="x", is_active=True)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as runtime_cls:
            runtime_cls.return_value.image.return_value = {
                "success": True,
                "data": [{"url": "https://example.com/a.png"}],
            }
            with patch("app.modules.ai.controller.aiapi.model.MediaAssetService") as media_cls:
                result = _run_sync_image_pipeline(payload=payload, current_user_id=user.id)

        self.assertTrue(result["success"])
        media_cls.return_value.create_from_ai_result.assert_called_once()

    def test_create_from_ai_result_base64_transfer_failure_marks_asset_failed(self):
        service = MediaAssetService(self.session)
        assets = service.create_from_ai_result(
            task_type="image",
            result={"data": [{"b64_json": "not-base64", "mime_type": "image/png"}]},
            request_payload={"prompt": "draw"},
            source_type="ai_sync",
            created_by=1,
        )

        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.status, "failed")
        self.assertIn("base64", asset.error_message)

    def test_create_from_ai_result_data_url_is_treated_as_base64_and_saved(self):
        payload = "data:image/png;base64," + base64.b64encode(b"inline-png").decode()
        storage = Mock()
        storage.save.return_value = "/uploads/20260512/inline.png"

        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            assets = MediaAssetService(self.session).create_from_ai_result(
                task_type="image",
                result={"data": [{"url": payload}]},
                request_payload={"prompt": "draw"},
                source_type="ai_sync",
                created_by=1,
            )

        self.assertEqual(len(assets), 1)
        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.status, "success")
        self.assertEqual(asset.storage_url, "/uploads/20260512/inline.png")
        self.assertEqual(asset.mime_type, "image/png")

    def test_create_from_ai_result_prefers_top_level_data_and_avoids_duplicate_raw_data(self):
        payload = base64.b64encode(b"dup-png").decode()
        storage = Mock()
        storage.save.return_value = "/uploads/20260512/dedup.png"

        with patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage):
            assets = MediaAssetService(self.session).create_from_ai_result(
                task_type="image",
                result={
                    "data": [{"b64_json": payload, "mime_type": "image/png"}],
                    "raw": {"data": [{"b64_json": payload, "mime_type": "image/png"}]},
                },
                request_payload={"prompt": "draw"},
                source_type="ai_sync",
                created_by=1,
            )

        self.assertEqual(len(assets), 1)
        rows = list(self.session.exec(select(MediaAsset).where(MediaAsset.delete_time == None)).all())  # noqa: E711
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "success")

    def test_media_page_compacts_large_original_url(self):
        asset = MediaAsset(
            asset_type="image",
            source_type="ai_sync",
            status="failed",
            original_url="data:image/png;base64," + ("a" * 5000),
            storage_url=None,
        )
        self.session.add(asset)
        self.session.commit()

        result = MediaAssetService(self.session).page(
            type(
                "Q",
                (),
                {
                    "page": 1,
                    "size": 20,
                    "eq_filters": {},
                    "like_filters": {},
                    "raw_params": {},
                    "keyword": None,
                    "order": None,
                    "sort": None,
                    "keyword_fields": (),
                    "order_fields": (),
                    "select_fields": (),
                    "add_order_by": (),
                    "where_handler": None,
                },
            )()
        )
        row = result.items[0]
        self.assertIsNone(row["originalUrl"])
        self.assertTrue(row["hasInlineOriginal"])
        self.assertGreater(row["originalUrlLength"], 4000)

    def test_media_info_keeps_preview_for_large_original_url(self):
        asset = MediaAsset(
            asset_type="image",
            source_type="ai_sync",
            status="failed",
            original_url="data:image/png;base64," + ("a" * 5000),
            storage_url=None,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        row = MediaAssetService(self.session).info(asset.id)
        self.assertTrue(row["hasInlineOriginal"])
        self.assertGreater(row["originalUrlLength"], 4000)
        self.assertTrue(row["originalUrlPreview"].startswith("data:image/png;base64,"))

    def test_rejects_localhost_and_private_remote_urls(self):
        with self.assertRaises(ValueError):
            _validate_remote_url("http://localhost/image.png")
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 0))]):
            with self.assertRaises(ValueError):
                _validate_remote_url("https://example.com/image.png")

    def test_allows_allowed_host_resolved_to_proxy_benchmark_network(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("198.18.0.6", 0))]):
            _validate_remote_url("https://ark-content-generation-v2-cn-beijing.tos-cn-beijing.volces.com/image.png")

    def test_rejects_unlisted_host_resolved_to_proxy_benchmark_network(self):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("198.18.0.6", 0))]):
            with self.assertRaises(ValueError):
                _validate_remote_url("https://example.com/image.png")

    def test_allowed_host_still_rejects_private_and_loopback_addresses(self):
        for address in ("10.0.0.1", "127.0.0.1"):
            with patch("socket.getaddrinfo", return_value=[(None, None, None, None, (address, 0))]):
                with self.assertRaises(ValueError):
                    _validate_remote_url(
                        "https://ark-content-generation-v2-cn-beijing.tos-cn-beijing.volces.com/image.png"
                    )

    def test_proxy_image_success(self):
        from app.modules.media.controller.admin.asset import MediaAssetController
        controller = MediaAssetController()
        user = User(id=1, username="admin")

        with patch("app.modules.media.controller.admin.asset._validate_remote_url", return_value=("https://1.2.3.4/pic.jpg", "example.com")), \
             patch("app.modules.media.controller.admin.asset._download_remote_file", return_value=(b"fake-image-bytes", "image/jpeg")):
            response = controller.proxy_image(url="https://example.com/pic.jpg", current_user=user)
            self.assertEqual(response.body, b"fake-image-bytes")
            self.assertEqual(response.media_type, "image/jpeg")
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_proxy_image_handles_failure(self):
        from app.modules.media.controller.admin.asset import MediaAssetController
        from fastapi import HTTPException
        controller = MediaAssetController()
        user = User(id=1, username="admin")

        with patch("app.modules.media.controller.admin.asset._validate_remote_url", side_effect=ValueError("不允许访问内网地址")):
            with self.assertRaises(HTTPException) as ctx:
                controller.proxy_image(url="http://127.0.0.1/evil.png", current_user=user)
            self.assertEqual(ctx.exception.status_code, 400)

    def _make_user(self, user_id: int, *, super_admin: bool = False) -> User:
        return User(
            id=user_id,
            username=f"user{user_id}",
            full_name=f"user{user_id}",
            password_hash="x",
            is_active=True,
            is_super_admin=super_admin,
        )

    def test_proxy_image_local_file_requires_ownership(self):
        """本地分支按文件级归属（storage_url+created_by）放行：本人/超管可读，他人 400"""
        import tempfile
        from pathlib import Path

        from fastapi import HTTPException

        from app.modules.media.controller.admin.asset import MediaAssetController

        asset = MediaAsset(
            asset_type="image",
            source_type="upload",
            original_url="https://example.com/own.png",
            storage_url="/uploads/2026/test/own.png",
            status="success",
            created_by=2,
        )
        self.session.add(asset)
        self.session.commit()

        controller = MediaAssetController()
        owner = self._make_user(2)
        stranger = self._make_user(1)
        super_admin = self._make_user(1, super_admin=True)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "2026" / "test"
            target.mkdir(parents=True)
            (target / "own.png").write_bytes(b"local-bytes")
            with patch("app.modules.media.controller.admin.asset.DEFAULT_UPLOAD_DIR", Path(tmp)):
                # 本人：命中本地文件直接返回
                response = controller.proxy_image(
                    url="https://example.com/own.png", current_user=owner, session=self.session
                )
                self.assertIn("own.png", str(response.path))
                # 超管：放行
                response = controller.proxy_image(
                    url="https://example.com/own.png", current_user=super_admin, session=self.session
                )
                self.assertIn("own.png", str(response.path))
                # 陌生人：归属不命中 → 不走本地分支，落入远程分支（mock 抛错 → 400）
                with patch(
                    "app.modules.media.controller.admin.asset._validate_remote_url",
                    side_effect=ValueError("不允许访问内网地址"),
                ):
                    with self.assertRaises(HTTPException) as ctx:
                        controller.proxy_image(
                            url="https://example.com/own.png", current_user=stranger, session=self.session
                        )
                    self.assertEqual(ctx.exception.status_code, 400)

    def test_proxy_image_local_path_escape_rejected(self):
        """storage_url 含路径逃逸（../../）时即使文件存在也拒绝走本地分支"""
        import tempfile
        from pathlib import Path

        from fastapi import HTTPException

        from app.modules.media.controller.admin.asset import MediaAssetController

        asset = MediaAsset(
            asset_type="image",
            source_type="upload",
            original_url="/uploads/../../evil.txt",
            storage_url="/uploads/../../evil.txt",
            status="success",
            created_by=1,
        )
        self.session.add(asset)
        self.session.commit()

        controller = MediaAssetController()
        owner = self._make_user(1)

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.modules.media.controller.admin.asset.DEFAULT_UPLOAD_DIR", Path(tmp)), patch(
                "app.modules.media.controller.admin.asset.os.path.isfile", return_value=True
            ), patch(
                "app.modules.media.controller.admin.asset._validate_remote_url",
                side_effect=ValueError("不允许访问内网地址"),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    controller.proxy_image(
                        url="/uploads/../../evil.txt", current_user=owner, session=self.session
                    )
                self.assertEqual(ctx.exception.status_code, 400)

    def test_proxy_image_forces_download_for_non_inline_mime(self):
        """远程声明的 text/html / SVG / 缺失 MIME 一律降级为附件下载，仅图片 inline"""
        from app.modules.media.controller.admin.asset import MediaAssetController

        controller = MediaAssetController()
        user = self._make_user(1, super_admin=True)

        for mime in ("text/html", "image/svg+xml", None):
            with patch(
                "app.modules.media.controller.admin.asset._validate_remote_url",
                return_value=("https://1.2.3.4/p.html", "example.com"),
            ), patch(
                "app.modules.media.controller.admin.asset._download_remote_file",
                return_value=(b"payload", mime),
            ):
                response = controller.proxy_image(url="https://example.com/p.html", current_user=user)
                self.assertEqual(response.media_type, "application/octet-stream")
                self.assertTrue(response.headers.get("content-disposition", "").startswith("attachment"))

        with patch(
            "app.modules.media.controller.admin.asset._validate_remote_url",
            return_value=("https://1.2.3.4/pic.jpg", "example.com"),
        ), patch(
            "app.modules.media.controller.admin.asset._download_remote_file",
            return_value=(b"payload", "image/jpeg; charset=binary"),
        ):
            response = controller.proxy_image(url="https://example.com/pic.jpg", current_user=user)
            self.assertEqual(response.media_type, "image/jpeg")
            self.assertTrue(response.headers.get("content-disposition", "").startswith("inline"))

    def test_add_strips_client_controlled_fields(self):
        """add 剥离客户端提交的 storage_url/status/created_by，归属取请求用户"""
        from app.modules.media.model.media import MediaAssetCreateRequest

        entity = MediaAssetService(self.session).add(
            MediaAssetCreateRequest(
                asset_type="image",
                source_type="ai_sync",
                original_url="https://example.com/x.png",
                storage_url="/uploads/evil.png",
                status="success",
                created_by=99,
            ),
            current_user=self._make_user(7),
        )
        self.assertIsNone(entity.storage_url)
        self.assertEqual(entity.status, "pending")
        self.assertEqual(entity.created_by, 7)

    def test_update_ignores_protected_fields(self):
        """update 剥离 storage_url/status/created_by，其余字段正常更新"""
        from app.modules.media.model.media import MediaAssetUpdateRequest

        asset = MediaAsset(
            asset_type="image",
            source_type="upload",
            storage_url="/uploads/a.png",
            status="success",
            created_by=1,
            file_name="old.png",
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        MediaAssetService(self.session).update(
            MediaAssetUpdateRequest(
                id=asset.id,
                storage_url="/uploads/evil.png",
                status="pending",
                created_by=99,
                file_name="new.png",
            )
        )

        refreshed = self.session.get(MediaAsset, asset.id)
        self.assertEqual(refreshed.storage_url, "/uploads/a.png")
        self.assertEqual(refreshed.status, "success")
        self.assertEqual(refreshed.created_by, 1)
        self.assertEqual(refreshed.file_name, "new.png")


if __name__ == "__main__":
    unittest.main()

