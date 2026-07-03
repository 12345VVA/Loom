"""Phase 5 任务状态机修复测试。

覆盖：
- 5.5 (P1-8): AI 任务 cancel 同步 DB status='cancelled' + 释放治理并发计数
- 5.6 (P1-9): AI 任务 retry 清旧 celery_task_id（revoke + 置空 + 写入新 id）
- 5.7 (P1-13): task once() 防重放锁（高频调用只触发一次 .delay()）
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.ai.model.ai import (
    AiGenerationTask,
    AiRuntimeInvocation,
)
from app.modules.ai.service.ai_service import AiGenerationTaskService, AiGovernanceService
from app.modules.task.model.task import TaskInfo
from app.modules.task.service.task_service import TaskInfoService


class Phase5TaskStateTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    # ------------------------------------------------------------------
    # Task 5.5 (P1-8): cancel 同步 DB status='cancelled' + 释放治理并发计数
    # ------------------------------------------------------------------
    def test_cancel_updates_db_status_and_releases_governance_counter(self):
        """cancel 后 DB status='cancelled'、progress=100、finished_at 已写，
        且调用 AiGovernanceService.release_for_generation_task 释放并发计数。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            profile_code="pf-test",
            status="running",
            progress=42,
            celery_task_id="old-celery-id-111",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = AiGenerationTaskService(self.session)
        with patch("app.celery_app.celery_app") as celery_mock, \
                patch.object(
                    AiGovernanceService, "release_for_generation_task", return_value=1
                ) as release_mock:
            result = svc.cancel(task.id)

        # revoke 调用：terminate=True，确保 worker 立即停止
        celery_mock.control.revoke.assert_called_once_with("old-celery-id-111", terminate=True)
        # 治理并发计数释放被调用一次
        release_mock.assert_called_once()
        # 返回值
        self.assertTrue(result["success"])
        # DB 状态
        self.session.refresh(task)
        self.assertEqual(task.status, "cancelled")
        self.assertEqual(task.progress, 100)
        self.assertIsNotNone(task.finished_at)

    def test_cancel_skips_release_for_terminal_status(self):
        """终态任务（success/failed/cancelled）幂等返回，不重复 revoke/release。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            status="success",
            progress=100,
            celery_task_id="old-celery-id-222",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = AiGenerationTaskService(self.session)
        with patch("app.celery_app.celery_app") as celery_mock, \
                patch.object(
                    AiGovernanceService, "release_for_generation_task", return_value=0
                ) as release_mock:
            result = svc.cancel(task.id)

        celery_mock.control.revoke.assert_not_called()
        release_mock.assert_not_called()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "success")

    def test_cancel_releases_running_invocation_via_governance_service(self):
        """集成验证：cancel 触发 release_for_generation_task 收尾 running invocation。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            profile_code="pf-int",
            status="running",
            progress=10,
            celery_task_id="old-celery-id-333",
            created_by=99,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        # 关联一个 running invocation（模拟 begin() 预占但未 finish 的场景）
        # 新实现 release_for_generation_task 按 task_id 精确匹配，故 invocation 须关联 task
        invocation = AiRuntimeInvocation(
            invocation_id="inv-1",
            user_id=99,
            task_id=task.id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(invocation)
        self.session.commit()

        svc = AiGenerationTaskService(self.session)
        with patch("app.celery_app.celery_app"):
            result = svc.cancel(task.id)

        self.assertTrue(result["success"])
        # invocation 被 release_for_generation_task 收尾
        self.session.refresh(invocation)
        self.assertEqual(invocation.status, "error")
        self.assertIsNotNone(invocation.finished_at)
        # 任务状态
        self.session.refresh(task)
        self.assertEqual(task.status, "cancelled")

    # ------------------------------------------------------------------
    # Task 5.6 (P1-9): retry 清旧 celery_task_id（revoke + 置空 + 写入新 id）
    # ------------------------------------------------------------------
    def test_retry_revokes_old_celery_task_and_records_new_id(self):
        """retry 时旧 celery_task_id 被 revoke + DB 中写入新 celery_task_id。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            profile_code="pf-retry",
            status="failed",
            progress=100,
            celery_task_id="old-celery-id-999",
            error_message="boom",
            retry_count=0,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = AiGenerationTaskService(self.session)
        new_async = MagicMock()
        new_async.id = "new-celery-id-000"

        with patch("app.celery_app.celery_app") as celery_mock, \
                patch(
                    "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task"
                ) as exec_task_mock:
            exec_task_mock.apply_async.return_value = new_async
            result = svc.retry(task.id)

        # 旧任务被 revoke（terminate=True）
        celery_mock.control.revoke.assert_called_once_with("old-celery-id-999", terminate=True)
        # 新任务入队（按队列路由）
        exec_task_mock.apply_async.assert_called_once()
        _, kwargs = exec_task_mock.apply_async.call_args
        self.assertEqual(kwargs.get("queue"), "ai.chat")
        # 返回值携带新 celeryTaskId
        self.assertTrue(result["success"])
        self.assertEqual(result["celeryTaskId"], "new-celery-id-000")
        # DB 状态：celery_task_id 已被替换为新的
        self.session.refresh(task)
        self.assertEqual(task.celery_task_id, "new-celery-id-000")
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.progress, 0)
        self.assertIsNone(task.error_message)
        self.assertIsNone(task.started_at)
        self.assertIsNone(task.finished_at)
        self.assertEqual(task.retry_count, 1)

    def test_retry_rejects_non_failed_task(self):
        """非 failed/cancelled 状态的任务不允许 retry。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            status="running",
            progress=50,
            celery_task_id="running-celery-id",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        from fastapi import HTTPException

        svc = AiGenerationTaskService(self.session)
        with patch("app.celery_app.celery_app") as celery_mock, \
                patch(
                    "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task"
                ) as exec_task_mock:
            with self.assertRaises(HTTPException) as cm:
                svc.retry(task.id)
            self.assertEqual(cm.exception.status_code, 400)

        celery_mock.control.revoke.assert_not_called()
        exec_task_mock.apply_async.assert_not_called()

    def test_retry_without_old_celery_id_skips_revoke(self):
        """旧 celery_task_id 为空时跳过 revoke，但仍正常入队新任务。"""
        task = AiGenerationTask(
            task_type="chat",
            scenario="default",
            status="cancelled",
            progress=100,
            celery_task_id=None,
            retry_count=2,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = AiGenerationTaskService(self.session)
        new_async = MagicMock()
        new_async.id = "fresh-celery-id"

        with patch("app.celery_app.celery_app") as celery_mock, \
                patch(
                    "app.modules.ai.tasks.generation_tasks.execute_ai_generation_task"
                ) as exec_task_mock:
            exec_task_mock.apply_async.return_value = new_async
            result = svc.retry(task.id)

        celery_mock.control.revoke.assert_not_called()
        exec_task_mock.apply_async.assert_called_once()
        self.assertEqual(result["celeryTaskId"], "fresh-celery-id")
        self.session.refresh(task)
        self.assertEqual(task.celery_task_id, "fresh-celery-id")
        self.assertEqual(task.retry_count, 3)

    # ------------------------------------------------------------------
    # Task 5.7 (P1-13): task once() 防重放锁（高频调用只触发一次）
    # ------------------------------------------------------------------
    def test_once_dedup_lock_only_triggers_once(self):
        """高频调用 once() 时，仅第一次 SETNX 成功并触发 .delay()，其余被跳过。"""
        task = TaskInfo(
            name="t-once",
            status=1,
            service="some.service.method",
            cron="*/5 * * * *",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = TaskInfoService(self.session)

        # 模拟 SETNX：第一次成功，后续失败（key 已存在）
        nx_results = iter([True, False, False, False])
        with patch(
            "app.modules.base.service.cache_service.cache_set_nx",
            side_effect=lambda *a, **kw: next(nx_results),
        ) as nx_mock, \
                patch(
                    "app.modules.task.tasks.system_tasks.execute_system_task"
                ) as exec_mock:
            results = [svc.once(task.id) for _ in range(4)]

        # SETNX 被调用 4 次（每次 once 都尝试获取锁）
        self.assertEqual(nx_mock.call_count, 4)
        # 但 .delay() 只触发 1 次（仅第一次成功获取锁的请求）
        exec_mock.delay.assert_called_once_with(task.id)
        # 返回值：第一次成功，后续跳过
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertFalse(results[2]["success"])
        self.assertFalse(results[3]["success"])

    def test_once_dedup_lock_key_and_ttl(self):
        """dedup_key 形如 task:once:{id}，TTL=300 秒。"""
        task = TaskInfo(
            name="t-ttl",
            status=1,
            service="some.service.method",
            cron="*/5 * * * *",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        svc = TaskInfoService(self.session)
        with patch(
            "app.modules.base.service.cache_service.cache_set_nx", return_value=True
        ) as nx_mock, \
                patch("app.modules.task.tasks.system_tasks.execute_system_task"):
            svc.once(task.id)

        nx_mock.assert_called_once()
        args, kwargs = nx_mock.call_args
        # 签名：cache_set_nx(key, value, ttl_seconds=...)
        self.assertEqual(args[0], f"task:once:{task.id}")
        self.assertEqual(kwargs.get("ttl_seconds"), 300)

    def test_once_returns_404_when_task_missing(self):
        """任务不存在时返回 404。"""
        from fastapi import HTTPException

        svc = TaskInfoService(self.session)
        with patch("app.modules.base.service.cache_service.cache_set_nx") as nx_mock, \
                patch("app.modules.task.tasks.system_tasks.execute_system_task") as exec_mock:
            with self.assertRaises(HTTPException) as cm:
                svc.once(99999)
            self.assertEqual(cm.exception.status_code, 404)

        nx_mock.assert_not_called()
        exec_mock.delay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
