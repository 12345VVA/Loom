"""工作流产物三期（瘦身与清理）测试。

- 执行日志过期清理：分批删行、载荷文件回收、顺序（先删行后删文件）
- 孤儿载荷回收：存活集差集、mtime 宽限期、软删行回收、S3 跳过、前缀过滤
- 实例删除级联：软删子表、清空 state_data、载荷文件删除、running 拒绝
- failed 资产重试：窗口挑选、成功/失败路径、limit
- eval offload 还原：state_data 裸读 bug 修复回归
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.framework.storage import LocalStorageProvider, StorageService, offload_payload
from app.modules.base.model.auth import User
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact
from app.modules.workflow.service.cleanup_service import WorkflowCleanupService
from app.modules.workflow.service.workflow_service import WorkflowInstanceService


def _super() -> User:
    return User(id=1, username="admin", full_name="admin", password_hash="x", is_active=True, is_super_admin=True)


def _tmp_storage() -> tuple[StorageService, str]:
    tmp = tempfile.mkdtemp(prefix="loom_cleanup_")
    return StorageService(LocalStorageProvider(upload_dir=tmp)), tmp


def _patch_storage(service: StorageService):
    return patch("app.framework.storage.StorageService.get_instance", return_value=service)


def _iso(dt: datetime) -> datetime:
    return dt


class SweepExecutionLogsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage = Mock()
        definition = WorkflowDefinition(code="wf", name="WF", graph_json="{}", is_active=True, user_id=1)
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        self.instance = WorkflowInstance(definition_id=definition.id, thread_id="t", status="success")
        self.session.add(self.instance)
        self.session.commit()
        self.session.refresh(self.instance)

    def tearDown(self):
        self.session.close()

    def _log(self, *, age_days: float, input_ref: str | None = None, output_ref: str | None = None):
        created = datetime.now(UTC) - timedelta(days=age_days)
        log = WorkflowExecutionLog(
            instance_id=self.instance.id,
            node_id="n1",
            node_name="N",
            node_type="llm",
            input_data="{}",
            output_data="{}",
            input_storage_ref=input_ref,
            output_storage_ref=output_ref,
            created_at=created,
            updated_at=created,
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def test_old_logs_removed_and_refs_deleted(self):
        old = self._log(age_days=120, input_ref="/uploads/old_in.json", output_ref="/uploads/old_out.json")
        fresh = self._log(age_days=1)
        service = Mock()

        with _patch_storage(service):
            removed = WorkflowCleanupService(self.session).sweep_execution_logs(keep_days=90)

        self.assertEqual(removed, 1)
        self.assertIsNone(self.session.get(WorkflowExecutionLog, old.id))
        self.assertIsNotNone(self.session.get(WorkflowExecutionLog, fresh.id))
        deleted_refs = {call.args[0] for call in service.delete.call_args_list}
        self.assertEqual(deleted_refs, {"/uploads/old_in.json", "/uploads/old_out.json"})

    def test_file_delete_failure_does_not_break_sweep(self):
        self._log(age_days=120, output_ref="/uploads/x.json")
        service = Mock()
        service.delete.side_effect = RuntimeError("io error")

        with _patch_storage(service):
            removed = WorkflowCleanupService(self.session).sweep_execution_logs(keep_days=90)

        self.assertEqual(removed, 1)


class SweepOrphanPayloadsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage, self.tmp = _tmp_storage()
        self.definition = WorkflowDefinition(code="wf", name="WF", graph_json="{}", is_active=True, user_id=1)
        self.session.add(self.definition)
        self.session.commit()
        self.session.refresh(self.definition)
        self.instance = WorkflowInstance(definition_id=self.definition.id, thread_id="t", status="success")
        self.session.add(self.instance)
        self.session.commit()
        self.session.refresh(self.instance)

    def tearDown(self):
        self.session.close()

    def _make_file(self, name: str, *, age_hours: float) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")
        old = (datetime.now().timestamp()) - age_hours * 3600
        os.utime(path, (old, old))
        return path

    def test_orphans_removed_alive_kept_grace_respected(self):
        # 存活 ref：instance 引用
        self.instance.state_data_ref = "/uploads/wf_payload_alive.json"
        self.session.add(self.instance)
        # 软删 artifact 的 ref（应被回收）
        self.session.add(
            WorkflowArtifact(
                instance_id=self.instance.id,
                definition_id=self.definition.id,
                user_id=1,
                field_key="old",
                asset_type="text",
                content="x",
                content_ref="/uploads/wf_payload_softdel.json",
                delete_time=datetime.now(UTC),
            )
        )
        self.session.commit()

        alive = self._make_file("wf_payload_alive.json", age_hours=48)
        softdel = self._make_file("wf_payload_softdel.json", age_hours=48)
        orphan = self._make_file("wf_payload_orphan.json", age_hours=48)
        fresh_orphan = self._make_file("wf_payload_fresh.json", age_hours=1)
        not_payload = self._make_file("user_upload.png", age_hours=48)

        with _patch_storage(self.storage):
            removed = WorkflowCleanupService(self.session).sweep_orphan_payloads(grace_hours=24)

        self.assertEqual(removed, 2)
        self.assertTrue(os.path.exists(alive))
        self.assertFalse(os.path.exists(softdel))
        self.assertFalse(os.path.exists(orphan))
        self.assertTrue(os.path.exists(fresh_orphan), "宽限期内的新文件跳过")
        self.assertTrue(os.path.exists(not_payload), "非 wf_payload 前缀不动")

    def test_skips_non_local_provider(self):
        s3_service = Mock()
        s3_service.provider = Mock(spec=[])  # 非 LocalStorageProvider
        with _patch_storage(s3_service):
            removed = WorkflowCleanupService(self.session).sweep_orphan_payloads()
        self.assertEqual(removed, 0)


class CascadeDeleteTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage = Mock()
        self.definition = WorkflowDefinition(code="wf", name="WF", graph_json="{}", is_active=True, user_id=1)
        self.session.add(self.definition)
        self.session.commit()
        self.session.refresh(self.definition)
        self.instance = WorkflowInstance(
            definition_id=self.definition.id,
            thread_id="th-1",
            status="success",
            state_data='{"a": 1}',
            state_data_ref="/uploads/wf_payload_state.json",
            user_id=1,
        )
        self.session.add(self.instance)
        self.session.commit()
        self.session.refresh(self.instance)
        self.log = WorkflowExecutionLog(
            instance_id=self.instance.id,
            node_id="n1",
            node_name="N",
            node_type="llm",
            input_data="REF_PREV",
            output_data="{}",
            output_storage_ref="/uploads/wf_payload_log.json",
        )
        self.artifact = WorkflowArtifact(
            instance_id=self.instance.id,
            definition_id=self.definition.id,
            user_id=1,
            field_key="story",
            asset_type="text",
            content="x",
            content_ref="/uploads/wf_payload_art.json",
        )
        self.session.add_all([self.log, self.artifact])
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_delete_cascades_and_clears_state(self):
        service = WorkflowInstanceService(self.session)
        with (
            _patch_storage(self.storage),
            patch(
                "app.modules.workflow.service.checkpointer.delete_thread_best_effort", return_value=True
            ) as mock_del_thread,
        ):
            service.delete([self.instance.id], current_user=_super(), soft_delete=True)

        # bulk update 会驱逐 session 内对象，断言前重新取
        instance = self.session.get(WorkflowInstance, self.instance.id)
        log = self.session.get(WorkflowExecutionLog, self.log.id)
        artifact = self.session.get(WorkflowArtifact, self.artifact.id)
        self.assertIsNotNone(instance.delete_time)
        self.assertEqual(instance.state_data, "")
        self.assertIsNone(instance.state_data_ref)
        self.assertIsNotNone(log.delete_time)
        self.assertIsNotNone(artifact.delete_time)

        deleted_refs = {call.args[0] for call in self.storage.delete.call_args_list}
        self.assertEqual(
            deleted_refs,
            {"/uploads/wf_payload_state.json", "/uploads/wf_payload_log.json", "/uploads/wf_payload_art.json"},
        )
        mock_del_thread.assert_called_once_with("th-1")

    def test_running_instance_rejected(self):
        self.instance.status = "running"
        self.session.add(self.instance)
        self.session.commit()
        service = WorkflowInstanceService(self.session)
        with self.assertRaises(HTTPException) as ctx:
            service.delete([self.instance.id], current_user=_super())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_storage_failure_still_deletes(self):
        self.storage.delete.side_effect = RuntimeError("io error")
        service = WorkflowInstanceService(self.session)
        with (
            _patch_storage(self.storage),
            patch("app.modules.workflow.service.checkpointer.delete_thread_best_effort", return_value=False),
        ):
            service.delete([self.instance.id], current_user=_super(), soft_delete=True)
        instance = self.session.get(WorkflowInstance, self.instance.id)
        self.assertIsNotNone(instance.delete_time, "文件删除失败不影响删除结果")


class RetryFailedTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage = Mock()
        self.storage.save.return_value = "/uploads/retry.png"

    def tearDown(self):
        self.session.close()

    def _asset(
        self,
        *,
        age_hours: float,
        status: str = "failed",
        url: str = "https://v.example.com/tmp.png",
        soft: bool = False,
    ):
        now = datetime.now(UTC)
        asset = MediaAsset(
            asset_type="image",
            source_type="workflow",
            status=status,
            original_url=url,
            created_by=1,
            updated_at=now - timedelta(hours=age_hours),
            delete_time=now if soft else None,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def _patch_download(self, content: bytes = b"png"):
        """绕过 SSRF 白名单（测试 URL 非白名单域），直接 mock 下载与校验。"""
        return (
            patch(
                "app.modules.media.service.media_service._validate_remote_url",
                return_value=("https://v.example.com/tmp.png", "v.example.com"),
            ),
            patch(
                "app.modules.media.service.media_service._download_remote_file",
                return_value=(content, "image/png"),
            ),
        )

    def test_window_selection_and_outcomes(self):
        in_window = self._asset(age_hours=2)
        out_window = self._asset(age_hours=30)
        _soft = self._asset(age_hours=2, soft=True)
        no_url = MediaAsset(asset_type="image", source_type="workflow", status="failed", created_by=1)
        self.session.add(no_url)
        self.session.commit()

        p1, p2 = self._patch_download()
        with _patch_storage(self.storage), p1, p2:
            result = MediaAssetService(self.session).retry_failed(limit=100, window_hours=24)

        self.assertEqual(result["attempted"], 1, "只挑窗口内 failed+url 的存活资产")
        self.assertEqual(result["succeeded"], 1)
        self.session.refresh(in_window)
        self.assertEqual(in_window.status, "success")
        self.session.refresh(out_window)
        self.assertEqual(out_window.status, "failed", "窗口外保持 failed")

    def test_limit_caps_attempts(self):
        for _ in range(3):
            self._asset(age_hours=1)
        p1, p2 = self._patch_download()
        with _patch_storage(self.storage), p1, p2:
            result = MediaAssetService(self.session).retry_failed(limit=2, window_hours=24)
        self.assertEqual(result["attempted"], 2)

    def test_retry_failure_updates_error(self):
        asset = self._asset(age_hours=1)
        p1, p2 = self._patch_download()
        with _patch_storage(Mock(save=Mock(side_effect=RuntimeError("still down")))), p1, p2:
            result = MediaAssetService(self.session).retry_failed(limit=10, window_hours=24)
        self.assertEqual(result["failed"], 1)
        self.session.refresh(asset)
        self.assertEqual(asset.status, "failed")
        self.assertIn("still down", asset.error_message)


class EvalOffloadResolveTest(unittest.TestCase):
    """eval 裸读 state_data 的 bug 修复回归：offload 实例的输出可还原。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage, self.tmp = _tmp_storage()

    def tearDown(self):
        self.session.close()

    def test_read_instance_result_resolves_offloaded_state(self):
        definition = WorkflowDefinition(code="wf", name="WF", graph_json="{}", is_active=True, user_id=1)
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        instance = WorkflowInstance(definition_id=definition.id, thread_id="t", status="success", user_id=1)
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)

        _big_output = {"workflow_output": {"story": "长" * 40000}}
        with _patch_storage(self.storage):
            _, ref = offload_payload('{"workflow_output": {"story": "' + "长" * 40000 + '"}}')
        instance.state_data = ""
        instance.state_data_ref = ref
        self.session.add(instance)
        self.session.commit()

        from app.modules.workflow_eval.service import eval_orchestrator

        with _patch_storage(self.storage), patch.object(eval_orchestrator, "engine", self.engine):
            result = eval_orchestrator.read_instance_result(instance.id)

        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["output"])
        self.assertEqual(result["output"]["story"], "长" * 40000)


if __name__ == "__main__":
    unittest.main()
