"""工作流转存归属（一期）测试。

- create_from_ai_result 的 workflow 归属参数落库
- _persist_image_to_media 从 workflow_instance_id_ctx 取实例，补 created_by/definition_id/node_id
- ctx 未设置（单节点测试路径）/实例已删 → 归属空、不抛
- 转存失败 → failed 行带归属列（无双写）
- md5 去重按 created_by 隔离（跨用户不复用，避免 /uploads 归属校验 403）
"""

from __future__ import annotations

import base64
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.logging import workflow_instance_id_ctx
from app.modules.base.model.auth import User
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.workflow_service import _persist_image_to_media

_PNG = base64.b64encode(b"wf-png").decode()


def _result() -> dict:
    return {"provider": "volc", "model": "seedream", "data": [{"b64_json": _PNG, "mime_type": "image/png"}]}


class MediaWorkflowAttributionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.storage = Mock()
        self.storage.save.return_value = "/uploads/20260920/wf.png"

    def tearDown(self):
        self.session.close()

    def _patch_storage(self):
        return patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=self.storage)

    def _patch_session_local(self):
        factory = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        return patch("app.core.database.SessionLocal", factory)

    def _make_instance(self, user_id: int = 7) -> WorkflowInstance:
        definition = WorkflowDefinition(
            code="wf1", name="WF1", graph_json="{}", is_active=True, current_version_id=1, user_id=user_id
        )
        self.session.add(definition)
        self.session.commit()
        self.session.refresh(definition)
        instance = WorkflowInstance(
            definition_id=definition.id, thread_id="t1", status="running", state_data="{}", user_id=user_id
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def test_create_from_ai_result_persists_workflow_attribution(self):
        """归属参数逐列落库"""
        with self._patch_storage():
            assets = MediaAssetService(self.session).create_from_ai_result(
                task_type="image",
                result=_result(),
                request_payload={"prompt": "draw"},
                source_type="workflow",
                created_by=7,
                profile_code="p1",
                workflow_instance_id=31,
                workflow_definition_id=8,
                workflow_node_id="node_cover",
            )
        asset = self.session.get(MediaAsset, assets[0].id)
        self.assertEqual(asset.created_by, 7)
        self.assertEqual(asset.workflow_instance_id, 31)
        self.assertEqual(asset.workflow_definition_id, 8)
        self.assertEqual(asset.workflow_node_id, "node_cover")
        self.assertEqual(asset.status, "success")

    def test_persist_image_to_media_fills_attribution_from_context(self):
        """ctx 关联实例：created_by=user_id、definition_id 落库，node_id 显式传入"""
        instance = self._make_instance(user_id=7)
        token = workflow_instance_id_ctx.set(instance.id)
        try:
            with self._patch_storage(), self._patch_session_local():
                url = _persist_image_to_media(_result(), {"prompt": "draw"}, "p1", "node_cover")
        finally:
            workflow_instance_id_ctx.reset(token)

        self.assertEqual(url, "/uploads/20260920/wf.png")
        asset = self.session.exec(select(MediaAsset)).one()
        self.assertEqual(asset.created_by, 7)
        self.assertEqual(asset.workflow_instance_id, instance.id)
        self.assertEqual(asset.workflow_definition_id, instance.definition_id)
        self.assertEqual(asset.workflow_node_id, "node_cover")

    def test_persist_image_to_media_without_context_leaves_attribution_empty(self):
        """单节点测试路径（ctx 未设置）：转存不抛，归属为空"""
        with self._patch_storage(), self._patch_session_local():
            url = _persist_image_to_media(_result(), {"prompt": "draw"}, "p1", "node_x")
        self.assertEqual(url, "/uploads/20260920/wf.png")
        asset = self.session.exec(select(MediaAsset)).one()
        self.assertIsNone(asset.created_by)
        self.assertIsNone(asset.workflow_instance_id)
        self.assertEqual(asset.workflow_node_id, "node_x")

    def test_persist_image_to_media_with_missing_instance_is_safe(self):
        """ctx 有值但实例已被删除：归属空、不抛"""
        token = workflow_instance_id_ctx.set(99999)
        try:
            with self._patch_storage(), self._patch_session_local():
                url = _persist_image_to_media(_result(), {"prompt": "draw"}, "p1", None)
        finally:
            workflow_instance_id_ctx.reset(token)
        self.assertEqual(url, "/uploads/20260920/wf.png")
        asset = self.session.exec(select(MediaAsset)).one()
        self.assertIsNone(asset.created_by)
        self.assertIsNone(asset.workflow_instance_id)

    def test_transfer_failure_failed_row_carries_attribution(self):
        """转存失败：_persist 约定抛 ValueError（回退临时 URL 在节点层），failed 行带归属列且无双写"""
        instance = self._make_instance(user_id=7)
        failing = Mock()
        failing.save.side_effect = RuntimeError("disk full")
        token = workflow_instance_id_ctx.set(instance.id)
        try:
            with (
                patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=failing),
                self._patch_session_local(),
            ):
                with self.assertRaises(ValueError):
                    _persist_image_to_media(_result(), {"prompt": "draw"}, "p1", "node_cover")
        finally:
            workflow_instance_id_ctx.reset(token)

        assets = list(self.session.exec(select(MediaAsset)).all())
        self.assertEqual(len(assets), 1, "不应产生重复 failed 行")
        asset = assets[0]
        self.assertEqual(asset.status, "failed")
        self.assertIn("disk full", asset.error_message)
        self.assertEqual(asset.created_by, 7)
        self.assertEqual(asset.workflow_instance_id, instance.id)
        self.assertEqual(asset.workflow_node_id, "node_cover")

    def test_dedup_isolated_by_created_by(self):
        """跨用户同 md5 不复用他人资产（复用会导致 /uploads 归属校验 403）"""
        service = MediaAssetService(self.session)
        with self._patch_storage():
            service.create_from_ai_result(
                task_type="image", result=_result(), request_payload={}, source_type="workflow", created_by=1
            )
            second = service.create_from_ai_result(
                task_type="image", result=_result(), request_payload={}, source_type="workflow", created_by=2
            )
        rows = list(self.session.exec(select(MediaAsset).where(MediaAsset.delete_time == None)).all())  # noqa: E711
        self.assertEqual(len(rows), 2)
        self.assertEqual(second[0].created_by, 2)
        self.assertEqual(second[0].status, "success")
        self.assertEqual({row.created_by for row in rows}, {1, 2})

    def test_dedup_same_user_still_hits(self):
        """同用户同 md5 仍去重：复用首行，新行被删（回归保护）"""
        service = MediaAssetService(self.session)
        with self._patch_storage():
            first = service.create_from_ai_result(
                task_type="image", result=_result(), request_payload={}, source_type="workflow", created_by=1
            )
            second = service.create_from_ai_result(
                task_type="image", result=_result(), request_payload={}, source_type="workflow", created_by=1
            )
        rows = list(self.session.exec(select(MediaAsset).where(MediaAsset.delete_time == None)).all())  # noqa: E711
        self.assertEqual(len(rows), 1)
        self.assertEqual(first[0].id, rows[0].id)
        self.assertNotEqual(second[0].id, rows[0].id)
        self.storage.save.assert_called_once()

    def test_non_admin_sees_own_workflow_assets(self):
        """归属修复后：非超管资源库可见本人 workflow 资产（stats 与 page 同一过滤机制）"""
        self.session.add(
            MediaAsset(
                asset_type="image", source_type="workflow", status="success", created_by=7, workflow_instance_id=31
            )
        )
        self.session.commit()
        stats = MediaAssetService(self.session).stats(
            User(id=7, username="u7", full_name="u7", password_hash="x", is_active=True)
        )
        self.assertEqual(stats["typeCounts"], {"image": 1})
        self.assertEqual(stats["sourceCounts"], {"workflow": 1})


if __name__ == "__main__":
    unittest.main()
