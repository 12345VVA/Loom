"""AI 产物媒体转存解耦测试（2026-10-18 批次1）。

覆盖：
- ingest_ai_task_now 核心语义：成功转存 / 幂等跳过 / 非 success 跳过 / 任务缺失跳过；
- 状态翻转隐患回归：execute_ai_generation_task 的转存派发失败不得翻转已成功任务；
- 补偿扫描：sweep_uningested_tasks 只补派「success 但从未落资产」的任务；
- registry 回调：ingest_ai_result_callback 返回落库资产数。
"""

from __future__ import annotations

import base64
import json
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.modules.ai.model.ai import AiGenerationTask
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.ingest_service import (
    ingest_ai_result_callback,
    ingest_ai_task_now,
    sweep_uningested_tasks,
)
from app.modules.media.service.media_service import MediaAssetService


def _make_image_task(session: Session, *, status: str = "success") -> AiGenerationTask:
    payload = base64.b64encode(b"png-bytes").decode()
    task = AiGenerationTask(
        task_type="image",
        scenario="default",
        profile_code="volc-image",
        status=status,
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
    if status == "success":
        task.finished_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _make_text_task(session: Session) -> AiGenerationTask:
    """文本类任务（chat）：success 且有 result_payload，但无任何媒体产物。"""
    task = AiGenerationTask(
        task_type="chat",
        scenario="default",
        profile_code="chat-profile",
        status="success",
        request_payload=json.dumps({"messages": [{"role": "user", "content": "hi"}]}),
        result_payload=json.dumps({"content": "hello"}),
    )
    task.finished_at = datetime.now(UTC)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _patch_storage():
    storage = Mock()
    storage.save.return_value = "/uploads/20260503/generated.png"
    return patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage)


class MediaIngestTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_ingest_ai_task_now_creates_asset(self):
        task = _make_image_task(self.session)

        with _patch_storage():
            result = ingest_ai_task_now(self.session, task.id)

        self.assertFalse(result["skipped"])
        self.assertEqual(len(result["assetIds"]), 1)
        asset = self.session.get(MediaAsset, result["assetIds"][0])
        self.assertEqual(asset.status, "success")
        self.assertEqual(asset.source_type, "ai_task")
        self.assertEqual(asset.source_task_id, task.id)

    def test_ingest_ai_task_now_idempotent(self):
        task = _make_image_task(self.session)

        with _patch_storage():
            first = ingest_ai_task_now(self.session, task.id)
            second = ingest_ai_task_now(self.session, task.id)

        self.assertFalse(first["skipped"])
        self.assertTrue(second["skipped"])
        rows = list(self.session.exec(select(MediaAsset).where(MediaAsset.delete_time == None)).all())  # noqa: E711
        self.assertEqual(len(rows), 1)

    def test_ingest_ai_task_now_skips_non_success_and_missing(self):
        running = _make_image_task(self.session, status="running")

        self.assertTrue(ingest_ai_task_now(self.session, running.id)["skipped"])
        self.assertTrue(ingest_ai_task_now(self.session, 999999)["skipped"])
        rows = list(self.session.exec(select(MediaAsset)).all())
        self.assertEqual(rows, [])

    def test_execute_task_dispatch_failure_keeps_success_status(self):
        """状态翻转隐患回归：转存派发失败（broker 宕）不得把已成功任务翻成 failed"""
        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        task = AiGenerationTask(
            task_type="image",
            status="pending",
            request_payload=json.dumps({"prompt": "draw"}),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        with (
            patch("app.modules.ai.tasks.generation_tasks.engine", self.engine),
            patch(
                "app.modules.ai.tasks.generation_tasks._invoke_runtime",
                return_value={"success": True, "data": [{"url": "https://example.com/a.png"}]},
            ),
            patch(
                "app.modules.ai.tasks.generation_tasks.celery_app.send_task",
                side_effect=ConnectionError("broker down"),
            ),
        ):
            result = execute_ai_generation_task(task.id)

        self.assertTrue(result["success"])
        self.session.expire_all()  # celery 任务用独立 session 提交，先失效本会话缓存再断言
        refreshed = self.session.get(AiGenerationTask, task.id)
        self.assertEqual(refreshed.status, "success")
        self.assertIsNotNone(refreshed.result_payload)

    def test_execute_task_dispatches_media_ingest(self):
        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        task = AiGenerationTask(
            task_type="image",
            status="pending",
            request_payload=json.dumps({"prompt": "draw"}),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        with (
            patch("app.modules.ai.tasks.generation_tasks.engine", self.engine),
            patch(
                "app.modules.ai.tasks.generation_tasks._invoke_runtime",
                return_value={"success": True, "data": [{"url": "https://example.com/a.png"}]},
            ),
            patch("app.modules.ai.tasks.generation_tasks.celery_app.send_task") as send,
        ):
            result = execute_ai_generation_task(task.id)

        self.assertTrue(result["success"])
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "media.ingest_ai_task")
        self.assertEqual(send.call_args.kwargs.get("args"), [task.id])

    def test_sweep_dispatches_only_uningested_success_tasks(self):
        uningested = _make_image_task(self.session)
        ingested = _make_image_task(self.session)
        failed = _make_image_task(self.session, status="failed")
        with _patch_storage():
            MediaAssetService(self.session).create_from_ai_task(ingested)

        with patch("app.core.database.engine", self.engine), patch("app.celery_app.celery_app.send_task") as send:
            result = sweep_uningested_tasks()

        self.assertEqual(result["scanned"], 1)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs.get("args"), [uningested.id])
        self.assertEqual(result["taskIds"], [uningested.id])
        # failed 任务不进入扫描口径（失败任务本就无产物可转存）
        self.assertNotIn(failed.id, result["taskIds"])

    def test_sweep_ignores_text_task_types(self):
        """chat/embedding/rerank 无媒体产物：不进补偿扫描（否则每小时重复派发），直接派发也跳过。"""
        text_task = _make_text_task(self.session)

        with patch("app.core.database.engine", self.engine), patch("app.celery_app.celery_app.send_task") as send:
            result = sweep_uningested_tasks()

        self.assertEqual(result["scanned"], 0)
        send.assert_not_called()
        self.assertTrue(ingest_ai_task_now(self.session, text_task.id)["skipped"])

    def test_ingest_ai_result_callback_returns_asset_count(self):
        task = _make_image_task(self.session)
        result_payload = json.loads(task.result_payload)

        with _patch_storage():
            count = ingest_ai_result_callback(
                self.session,
                task_type="image",
                result=result_payload,
                request_payload=json.loads(task.request_payload),
                source_type="ai_sync",
                created_by=7,
                profile_code="volc-image",
            )

        self.assertEqual(count, 1)
        asset = self.session.exec(
            select(MediaAsset).where(MediaAsset.source_type == "ai_sync")  # noqa: E712
        ).first()
        self.assertEqual(asset.created_by, 7)


if __name__ == "__main__":
    unittest.main()
