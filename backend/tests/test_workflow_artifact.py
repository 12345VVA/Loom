"""工作流产物流转（二期）测试。

- classify_artifacts：workflow_output 自适应分类全分支
- persist_workflow_artifacts：幂等（硬删旧行）、best-effort、超阈值 offload、image 反查 media_asset
- WorkflowArtifactService.delete：非本人 403（BaseAdminCrudService.delete 不走 DataScope，防 IDOR）
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.base.model.auth import User
from app.modules.media.model.media import MediaAsset
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact, WorkflowArtifactRead
from app.modules.workflow.service.artifact_crud_service import WorkflowArtifactService
from app.modules.workflow.service.artifact_service import (
    classify_artifacts,
    is_image_url,
    persist_workflow_artifacts,
)


class ClassifyArtifactsTest(unittest.TestCase):
    def test_dict_fields_classified(self):
        output = {
            "cover_image": "/uploads/20260920/a.jpeg",
            "online_image": "https://example.com/x.png?sig=1",
            "web_link": "https://example.com/page",
            "story": "第一段\n第二段",
            "empty": "   ",
            "count": 3,
            "flag": True,
            "noise": None,
            "inline": "data:image/png;base64,AAAA",
        }
        drafts = {d.field_key: d for d in classify_artifacts(output)}
        self.assertEqual(drafts["cover_image"].asset_type, "image")
        self.assertEqual(drafts["online_image"].asset_type, "image", "图片扩展名 URL（忽略 query）判 image")
        self.assertEqual(drafts["web_link"].asset_type, "text", "无扩展名 URL 防误判，按 text 保留可复制")
        self.assertEqual(drafts["story"].asset_type, "text")
        for skipped in ("empty", "count", "flag", "noise", "inline"):
            self.assertNotIn(skipped, drafts)

    def test_top_level_str_uses_output_key(self):
        """end 节点文本模式：workflow_output 为 str，field_key 固定 output"""
        drafts = classify_artifacts("纯文本输出")
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].field_key, "output")
        self.assertEqual(drafts[0].asset_type, "text")

    def test_scalar_list_expanded_with_path(self):
        drafts = classify_artifacts({"inner_images": ["/uploads/a.jpeg", "/uploads/b.jpeg"]})
        self.assertEqual([d.field_path for d in drafts], ["inner_images.0", "inner_images.1"])
        self.assertTrue(all(d.asset_type == "image" for d in drafts))

    def test_list_with_dict_and_dict_become_json(self):
        output = {
            "paragraphs": [{"text": "a"}, {"text": "b"}],
            "meta": {"author": "asu"},
        }
        drafts = {d.field_key: d for d in classify_artifacts(output)}
        self.assertEqual(drafts["paragraphs"].asset_type, "json")
        self.assertIn('"text": "a"', drafts["paragraphs"].value)
        self.assertEqual(drafts["meta"].asset_type, "json")

    def test_loop_inner_images_dict_list_extracted_as_images(self):
        output = {
            "cover_image": "/uploads/cover.jpeg",
            "inner_images": [
                {"image_url": "https://example.com/p1.png"},
                {"image_url": "https://example.com/p2.png"}
            ]
        }
        drafts = classify_artifacts(output)
        paths = [d.field_path for d in drafts if d.asset_type == "image"]
        self.assertIn("inner_images.0.image_url", paths)
        self.assertIn("inner_images.1.image_url", paths)
        self.assertEqual(len([d for d in drafts if d.asset_type == "image"]), 3)
        # json 整体并存：文案/失败信息不随图片提取丢失
        json_draft = next(d for d in drafts if d.asset_type == "json")
        self.assertEqual(json_draft.field_key, "inner_images")

    def test_dunder_src_internal_vars_skipped(self):
        """__src 内部通道变量（厂商临时 URL 专供下游节点 imageVariable 引用）不分类"""
        output = {
            "cover_image_url": "/uploads/cover.jpeg",
            "cover_image_url__src": "https://ark-content-generation.tos-cn-beijing.volces.com/tmp/u",
            "row": {"image": "/uploads/a.png", "image__src": "https://tos-x.volces.com/tmp/v"},
            "inner_images": [
                {"image_url": "/uploads/b.png", "image_url__src": "https://tos-x.volces.com/tmp/w"}
            ],
        }
        drafts = classify_artifacts(output)
        image_paths = [d.field_path for d in drafts if d.asset_type == "image"]
        # 顶层标量 field_path 为 None（field_key 才是 cover_image_url）
        self.assertEqual(image_paths, [None, "row.image", "inner_images.0.image_url"])
        # row 含图片子键不落 json；inner_images 落 json 整体（内容含 __src 供排查，不产生额外 image）
        json_drafts = [d for d in drafts if d.asset_type == "json"]
        self.assertEqual(len(json_drafts), 1)
        self.assertEqual(json_drafts[0].field_key, "inner_images")

    def test_duplicate_image_urls_deduped_across_fields(self):
        """循环快照重复携带外层图片（封面进每个迭代 dict）：同一 URL 全程仅保留首见"""
        cover = "/uploads/cover.jpeg"
        output = {
            "cover_image": cover,
            "inner_images": [
                {"image_url": "/uploads/p1.jpeg", "cover_image_url": cover},
                {"image_url": "/uploads/p2.jpeg", "cover_image_url": cover},
            ],
        }
        drafts = classify_artifacts(output)
        image_values = [d.value for d in drafts if d.asset_type == "image"]
        self.assertEqual(image_values.count(cover), 1, "封面只保留首见一条")
        self.assertEqual(len(image_values), 3, "封面 + 两张内页")

    def test_list_with_images_keeps_json_draft(self):
        """list 含图片时 json 整体并存：失败迭代的 error/文案不丢失"""
        output = {
            "inner_images": [
                {"image_url": "/uploads/p1.png", "caption": "第一页"},
                {"error": "图片生成超量限流"},
            ]
        }
        drafts = classify_artifacts(output)
        image_paths = [d.field_path for d in drafts if d.asset_type == "image"]
        self.assertEqual(image_paths, ["inner_images.0.image_url"])
        json_draft = next(d for d in drafts if d.asset_type == "json")
        self.assertEqual(json_draft.field_key, "inner_images")
        self.assertIn("超量限流", json_draft.value)
        self.assertIn("第一页", json_draft.value)

    def test_is_image_url_host_and_extension_rules(self):
        # 有扩展名时只按扩展名判定：存储桶上的音频/文档直链不误判为图片
        self.assertTrue(is_image_url("https://example.com/pic.png"))
        self.assertFalse(is_image_url("https://tos-cn-beijing.volces.com/audio.mp3"))
        self.assertFalse(is_image_url("https://bucket.oss-cn-hangzhou.aliyuncs.com/report.pdf"))
        # 无扩展名：受限对象存储域按 host 兜底（转存失败回退厂商临时 URL 场景）
        self.assertTrue(is_image_url("https://tos-cn-beijing.volces.com/obj/sign~noext"))
        self.assertTrue(is_image_url("https://bucket.oss-cn-hangzhou.aliyuncs.com/obj/noext"))
        self.assertTrue(is_image_url("https://bucket.cos.ap-guangzhou.myqcloud.com/obj/noext"))
        # 域级匹配：含 "cos." 的无关域名不再误判
        self.assertFalse(is_image_url("https://macos.dev/page"))
        self.assertFalse(is_image_url("https://foo.macos.dev/obj/noext"))

    def test_non_dict_non_str_top_level_yields_nothing(self):
        self.assertEqual(classify_artifacts(None), [])
        self.assertEqual(classify_artifacts(123), [])


class PersistArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)

    def _persist(self, output, engine=None):
        persist_workflow_artifacts(31, 8, 18, 7, "node_end", output, engine=engine or self.engine)

    def _rows(self):
        with Session(self.engine) as s:
            return list(s.exec(select(WorkflowArtifact).order_by(WorkflowArtifact.id)).all())

    def test_persists_rows_with_attribution(self):
        self._persist({"cover": "/uploads/20260920/a.jpeg", "story": "故事文本"})
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        by_key = {row.field_key: row for row in rows}
        self.assertEqual(by_key["cover"].asset_type, "image")
        self.assertEqual(by_key["cover"].storage_url, "/uploads/20260920/a.jpeg", "/uploads/ 无资产命中时直存展示地址")
        self.assertEqual(by_key["story"].user_id, 7)
        self.assertEqual(by_key["story"].node_id, "node_end")
        self.assertEqual(by_key["story"].version_id, 18)

    def test_persists_nothing_for_empty_output(self):
        self._persist(None)
        self._persist({})
        self.assertEqual(self._rows(), [])

    def test_idempotent_hard_deletes_old_rows(self):
        self._persist({"story": "v1"})
        self._persist({"story": "v2", "cover": "/uploads/b.png"})
        rows = self._rows()
        self.assertEqual(len(rows), 2, "旧产物硬删，不翻倍不堆积软删行")
        self.assertEqual(sorted(r.field_key for r in rows), ["cover", "story"])

    def test_image_resolves_media_asset_by_storage_then_original(self):
        with Session(self.engine) as s:
            by_storage = MediaAsset(
                asset_type="image", source_type="workflow", status="success",
                storage_url="/uploads/x.jpeg", original_url="https://v.example.com/tmp/1.png",
                created_by=7,
            )
            s.add(by_storage)
            s.commit()
            s.refresh(by_storage)

        self._persist({"cover": "/uploads/x.jpeg", "inner": "https://v.example.com/tmp/1.png"})

        rows = {r.field_key: r for r in self._rows()}
        self.assertEqual(rows["cover"].media_asset_id, by_storage.id)
        self.assertEqual(rows["inner"].media_asset_id, by_storage.id, "按厂商原始 URL 兜底命中")
        self.assertEqual(rows["inner"].storage_url, "/uploads/x.jpeg")

    def test_best_effort_swallows_engine_errors(self):
        """落库失败仅告警，不影响 success 终态（调用方在 workflow_tasks）"""
        broken = Mock()
        broken.connect.side_effect = RuntimeError("db down")
        # 不抛即通过
        self._persist({"story": "文本"}, engine=broken)

    def test_large_content_offloaded(self):
        with patch(
            "app.modules.workflow.service.artifact_service.offload_payload",
            return_value=("", "wf_payload_test.json"),
        ) as mock_offload:
            self._persist({"story": "长文本" * 10})
        mock_offload.assert_called_once()
        row = self._rows()[0]
        self.assertIsNone(row.content)
        self.assertEqual(row.content_ref, "wf_payload_test.json")

    def test_read_dto_uses_camel_alias(self):
        payload = WorkflowArtifactRead(
            id=1, instance_id=31, definition_id=8, field_key="cover", asset_type="image",
            created_at="2026-09-20T00:00:00Z", updated_at="2026-09-20T00:00:00Z",
        ).model_dump(by_alias=True)
        self.assertIn("instanceId", payload)
        self.assertIn("fieldKey", payload)
        self.assertIn("assetType", payload)


class ArtifactDeleteOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        for field in ("cover", "story"):
            self.session.add(
                WorkflowArtifact(
                    instance_id=31, definition_id=8, user_id=7, field_key=field,
                    asset_type="text", content="x",
                )
            )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def _user(self, user_id: int, super_admin: bool = False) -> User:
        return User(
            id=user_id, username=f"u{user_id}", full_name=f"u{user_id}",
            password_hash="x", is_active=True, is_super_admin=super_admin,
        )

    def _row(self, field_key: str) -> WorkflowArtifact:
        return self.session.exec(
            select(WorkflowArtifact).where(WorkflowArtifact.field_key == field_key)
        ).one()

    def test_delete_other_users_artifact_forbidden(self):
        svc = WorkflowArtifactService(self.session)
        row = self._row("cover")
        with self.assertRaises(HTTPException) as ctx:
            svc.delete([row.id], current_user=self._user(99))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_can_soft_delete(self):
        svc = WorkflowArtifactService(self.session)
        row = self._row("cover")
        # soft_delete=True 模拟 controller meta 注入后的调用形态
        svc.delete([row.id], current_user=self._user(7), soft_delete=True)
        self.session.refresh(row)
        self.assertIsNotNone(row.delete_time, "soft_delete 生效")

    def test_super_admin_can_delete_any(self):
        svc = WorkflowArtifactService(self.session)
        row = self._row("story")
        svc.delete([row.id], current_user=self._user(1, super_admin=True), soft_delete=True)
        self.session.refresh(row)
        self.assertIsNotNone(row.delete_time)


if __name__ == "__main__":
    unittest.main()
