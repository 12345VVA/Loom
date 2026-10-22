"""工作流生图节点 × Composer 桥接测试（P5）。

映射验收：4（软删 fail-fast 文案含资产名）5（archived 存量放行）12（回链指纹落库）
+ D6 合并注入 + media create_from_ai_result 回链提取。
AI 调用链（runtime/adapters）不做端到端 mock——插桩逻辑之外的行为由既有
test_image_ingress / test_media_ingest / adapter 测试覆盖。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, select

from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_PUBLISHED,
    AssetCharacter,
)
from app.modules.asset.service import composer
from app.modules.asset.service.composer import AssetNotFoundError, compose_for_node
from app.modules.base.model.sys import SysLog, SysParam
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaAssetService


def _pass_through_scheduler(value):
    if isinstance(value, list):
        return list(value)
    return value


class ComposeForNodeTestCase(unittest.TestCase):
    """compose_for_node：config 寻址 / 短会话加载 / 执行期状态语义。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[AssetCharacter.__table__, MediaAsset.__table__, SysParam.__table__, SysLog.__table__]
        )
        self.session = Session(self.engine)
        self.session.add(SysParam(name="s", key_name="assetGlobalNegativePrompt", data="blurry"))
        self.session.commit()
        patcher = patch.object(composer, "resolve_image_input_value", side_effect=_pass_through_scheduler)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _character(self, status: str = ASSET_STATUS_PUBLISHED, **kwargs) -> int:
        entity = AssetCharacter(
            code="hero",
            name="小白",
            status=status,
            created_by=7,
            appearance_prompt=kwargs.pop("appearance_prompt", "silver hair girl"),
            **kwargs,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity.id

    def test_node_compose_replaces_prompt(self):
        """config 三键生效：节点 prompt 作为用户正文进组装（正文存活，风格/场景缺失跳过）。"""
        asset_id = self._character()
        config = {"characterId": asset_id}
        result = compose_for_node(config, {}, "profile-1", None, "a knight on horseback", session=self.session)
        self.assertEqual(result.prompt, "silver hair girl\na knight on horseback")
        self.assertEqual(result.asset_refs, {"characterId": asset_id})

    def test_soft_deleted_fail_fast_with_name(self):
        """软删角色 → ValueError 中文文案含资产名（验收 4）；AssetError 不再二次包装。"""
        asset_id = self._character()
        entity = self.session.get(AssetCharacter, asset_id)
        entity.delete_time = __import__("datetime").datetime.now(__import__("datetime").UTC)
        self.session.add(entity)
        self.session.commit()

        # AssetError → ValueError 的翻译在 node_executors 插桩层（except AssetError 直出 str）
        with self.assertRaises(AssetNotFoundError) as ctx:
            compose_for_node({"characterId": asset_id}, {}, None, None, "x", session=self.session)
        self.assertIn("小白", str(ctx.exception))

    def test_archived_existing_reference_passes(self):
        """存量图引用 archived 角色 → 正常执行（验收 5，决策 #8）。"""
        asset_id = self._character(status=ASSET_STATUS_ARCHIVED)
        result = compose_for_node({"characterId": asset_id}, {}, None, None, "x", session=self.session)
        self.assertIn("silver hair girl", result.prompt)
        self.assertIn("ASSET_ARCHIVED_REF", [w.code for w in result.warnings])

    def test_draft_reference_fail_fast(self):
        """工作流执行期 draft 引用 fail-fast（权限矩阵：仅手工构造图可能出现）。"""
        from app.modules.asset.model.asset import ASSET_STATUS_DRAFT
        from app.modules.asset.service.composer import AssetStateError

        asset_id = self._character(status=ASSET_STATUS_DRAFT)
        with self.assertRaises(AssetStateError):
            compose_for_node({"characterId": asset_id}, {}, None, None, "x", session=self.session)

    def test_d6_node_image_merged_and_truncated(self):
        """D6：poryf 兜底 1 张 → 资产图占满配额，节点显式图被裁；返回 asset_refs 供回链。"""
        media = MediaAsset(asset_type="image", status="success", storage_url="/uploads/test/a.png")
        self.session.add(media)
        self.session.commit()
        self.session.refresh(media)
        asset_id = self._character(ref_image_ids=f"[{media.id}]")
        result = compose_for_node(
            {"characterId": asset_id}, {}, None, "http://cdn.example.com/n1.png", "x", session=self.session
        )
        self.assertEqual(result.reference_images, ["/uploads/test/a.png"])


class MediaIngestAssetRefTestCase(unittest.TestCase):
    """create_from_ai_result 回链提取（验收 12 的 media 侧）。"""

    def setUp(self):
        self.engine = make_test_engine(tables=[MediaAsset.__table__])
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_asset_refs_landed(self):
        """options 携带回链三键 → 落列 + 派生 source_*_id（D3 冗余列供计数）。"""
        result = {"data": [{"url": "http://vendor.example.com/a.png"}], "provider": "p", "model": "m"}
        request_payload = {
            "prompt": "p",
            "options": {
                "asset_refs": {"characterId": 11, "sceneId": 22},
                "composed_prompt_hash": "h" * 32,
                "composer_version": "1",
            },
        }
        assets = MediaAssetService(self.session).create_from_ai_result(
            task_type="image",
            result=result,
            request_payload=request_payload,
            source_type="workflow",
        )
        self.assertEqual(len(assets), 1)
        asset = self.session.exec(select(MediaAsset)).first()
        self.assertEqual(asset.source_character_id, 11)
        self.assertEqual(asset.source_scene_id, 22)
        self.assertIsNone(asset.source_style_id)
        self.assertEqual(asset.composed_prompt_hash, "h" * 32)
        self.assertEqual(asset.composer_version, "1")
        import json as _json

        self.assertEqual(_json.loads(asset.asset_refs), {"characterId": 11, "sceneId": 22})

    def test_no_asset_refs_stays_clean(self):
        """无资产引用 → 回链列全空（存量链路零影响）。"""
        result = {"data": [{"url": "http://vendor.example.com/a.png"}]}
        MediaAssetService(self.session).create_from_ai_result(
            task_type="image",
            result=result,
            request_payload={"prompt": "p", "options": {"size": "1024x1024"}},
            source_type="ai_sync",
        )
        asset = self.session.exec(select(MediaAsset)).first()
        self.assertIsNone(asset.asset_refs)
        self.assertIsNone(asset.source_character_id)
        self.assertIsNone(asset.composed_prompt_hash)

    def test_malformed_refs_ignored(self):
        """坏数据防御：非正整数引用值不落库。"""
        result = {"data": [{"url": "http://vendor.example.com/a.png"}]}
        MediaAssetService(self.session).create_from_ai_result(
            task_type="image",
            result=result,
            request_payload={"prompt": "p", "options": {"asset_refs": {"characterId": "x", "sceneId": -1}}},
            source_type="workflow",
        )
        asset = self.session.exec(select(MediaAsset)).first()
        self.assertIsNone(asset.asset_refs)


if __name__ == "__main__":
    unittest.main()
