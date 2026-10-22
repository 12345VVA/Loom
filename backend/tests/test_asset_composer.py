"""AssetPromptComposer 组装协议契约测试（P3，TDD 先行）。

契约唯一依据：设计文档附录 B（IP资产库模块设计-2026-10-22.md）。
映射验收标准：1（顺序/去重）4（软删 fail-fast）5（archived 放行）7（变量缺失）
8（悬空/锚定）9（渠道自适应/role）10（降级）11（警告）12（指纹）
+ 评审修订：size 覆盖三分支（P0-1）、profile=None（P2-3）、预算边界、合并注入（D6）。

渠道能力经 patch ``composer._resolve_channel`` 注入（真解析链 P5 由节点/端点测试覆盖，
自身解析行为依赖 ai 模块 RegistryService，属集成面）。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import unittest
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session

from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_PUBLISHED,
    COMPOSER_VERSION,
    AssetCharacter,
    AssetScene,
    AssetStyle,
)
from app.modules.asset.service import composer
from app.modules.asset.service.composer import (
    AssetAnchorError,
    AssetNotFoundError,
    AssetPromptBudgetError,
    AssetStateError,
    AssetVariableMissingError,
    ComposeInput,
    compose,
)
from app.modules.base.model.sys import SysParam
from app.modules.media.model.media import MediaAsset


def _pass_through_scheduler(value):
    """测试桩：URL 消费调度直通（调度自身行为由 test_image_ingress 覆盖）。"""
    if isinstance(value, list):
        return list(value)
    return value


class ComposerTestCase(unittest.TestCase):
    """组装协议主测试面（内存引擎 + 调度桩 + 渠道解析桩）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AssetCharacter.__table__,
                AssetScene.__table__,
                AssetStyle.__table__,
                MediaAsset.__table__,
                SysParam.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.user_id = 1
        # URL 消费调度直通（调度行为由 test_image_ingress 覆盖）
        patcher = patch.object(composer, "resolve_image_input_value", side_effect=_pass_through_scheduler)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    # --- 夹具 ---

    def _patch_channel(self, capabilities: list[str], adapter_type: str | None):
        """注入渠道解析结果（_resolve_channel 真实链在 P5 集成面覆盖）。"""
        patcher = patch.object(composer, "_resolve_channel", return_value=(capabilities, adapter_type))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _media_url(mid: int) -> str:
        return f"/uploads/test/{mid}.png"

    def _set_param(self, key: str, data: str):
        self.session.add(SysParam(name=key, key_name=key, data=data))
        self.session.commit()

    def _add_media(self, md5: str | None = None, status: str = "success") -> int:
        media = MediaAsset(asset_type="image", status=status, md5=md5)
        self.session.add(media)
        self.session.commit()
        self.session.refresh(media)
        media.storage_url = f"/uploads/test/{media.id}.png"
        self.session.add(media)
        self.session.commit()
        return media.id

    def _character(self, code: str = "hero", status: str = ASSET_STATUS_PUBLISHED, **kwargs) -> AssetCharacter:
        entity = AssetCharacter(
            code=code, name=kwargs.pop("name", "小白"), status=status, created_by=self.user_id, **kwargs
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def _scene(self, code: str = "cafe", status: str = ASSET_STATUS_PUBLISHED, **kwargs) -> AssetScene:
        entity = AssetScene(
            code=code, name=kwargs.pop("name", "咖啡馆"), status=status, created_by=self.user_id, **kwargs
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def _style(self, code: str = "anime", status: str = ASSET_STATUS_PUBLISHED, **kwargs) -> AssetStyle:
        entity = AssetStyle(
            code=code, name=kwargs.pop("name", "动漫风"), status=status, created_by=self.user_id, **kwargs
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def _compose(self, **kwargs) -> composer.ComposeResult:
        params: dict = {"user_prompt": "在长椅上看书", "variables": {}, "current_user_id": self.user_id}
        params.update(kwargs)
        return compose(self.session, ComposeInput(**params))

    def _warning_codes(self, result: composer.ComposeResult) -> list[str]:
        return [w.code for w in result.warnings]

    # --- 验收 1：组装顺序 / 空段 / 负面去重 ---

    def test_assembly_order_and_negative_dedup(self):
        style = self._style(appearance_prompt="anime style", negative_prompt="blurry")
        scene = self._scene(appearance_prompt="cozy cafe", negative_prompt="Blurry")
        character = self._character(appearance_prompt="silver hair girl", negative_prompt="extra fingers")

        result = self._compose(character=character, scene=scene, style=style)
        self.assertEqual(result.prompt, "anime style\ncozy cafe\nsilver hair girl\n在长椅上看书")
        # 负面四源大小写不敏感去重（Blurry 与 blurry 重复，保序留首现）
        self.assertEqual(result.negative_prompt, "blurry\nextra fingers")

    def test_empty_segments_skipped(self):
        """空片段（未配置/空白）跳过，不产生空行（验收 1）。"""
        entity = self._character(appearance_prompt="silver hair girl")
        result = self._compose(character=entity)
        self.assertEqual(result.prompt, "silver hair girl\n在长椅上看书")

    def test_global_negative_from_sys_param(self):
        """全局负面词走 sys_param 第四源（决策 #14），并参与去重。"""
        self._set_param("assetGlobalNegativePrompt", "extra fingers")
        entity = self._character(appearance_prompt="girl", negative_prompt="extra fingers")
        result = self._compose(character=entity)
        self.assertEqual(result.negative_prompt, "extra fingers")

    # --- 验收 4/5/2：软删 fail-fast / archived 放行 / 他人 draft 防御 ---

    def test_soft_deleted_fail_fast(self):
        entity = self._character()
        entity.delete_time = datetime.datetime.now(datetime.UTC)
        self.session.add(entity)
        self.session.commit()
        with self.assertRaises(AssetNotFoundError) as ctx:
            self._compose(character=entity)
        self.assertIn("小白", str(ctx.exception))

    def test_archived_passes_with_warning(self):
        """存量引用 archived 放行 + ASSET_ARCHIVED_REF warning（验收 5，决策 #8）。"""
        entity = self._character(status=ASSET_STATUS_ARCHIVED, appearance_prompt="girl")
        result = self._compose(character=entity)
        self.assertIn("girl", result.prompt)
        self.assertIn("ASSET_ARCHIVED_REF", self._warning_codes(result))

    def test_other_draft_rejected(self):
        """执行期防御：他人 draft 拒绝（选择器层已拦截，此处兜底，验收 2）。"""
        entity = self._character(status=ASSET_STATUS_DRAFT)
        with self.assertRaises(AssetStateError):
            self._compose(character=entity, current_user_id=999)

    # --- 验收 7：变量缺失 fail-fast / 渲染边界 ---

    def test_variable_missing_fail_fast(self):
        entity = self._character(appearance_prompt="silver hair girl, {{服装}}, {{发饰}}")
        with self.assertRaises(AssetVariableMissingError) as ctx:
            self._compose(character=entity, variables={"发饰": "红色发带"})
        self.assertIn("角色卡「小白」的变量「服装」未提供", str(ctx.exception))

    def test_variable_rendered_in_asset_segment_only(self):
        """占位仅在资产片段内生效；用户正文中的 {{}} 不展开（决策 #13）。"""
        entity = self._character(appearance_prompt="girl wearing {{服装}}")
        result = self._compose(character=entity, variables={"服装": "红裙"})
        self.assertIn("girl wearing 红裙", result.prompt)
        result2 = self._compose(character=entity, variables={"服装": "红裙"}, user_prompt="she wears {{服装}}")
        self.assertIn("she wears {{服装}}", result2.prompt)

    # --- 验收 8：悬空 / 锚定下限 ---

    def test_dangling_refs_skipped_with_warning(self):
        """3 张参考图 1 张悬空 → 注入其余 2 张 + REF_IMAGE_MISSING（验收 8）。"""
        self._set_param("assetDefaultReferenceImages", "4")
        m1, m2 = self._add_media(), self._add_media()
        entity = self._character(ref_image_ids=f'[{{"id": {m1}}}, {{"id": 990}}, {{"id": {m2}}}]')
        self._patch_channel(["image", "multi_reference_image"], "toapis")
        result = self._compose(character=entity)
        self.assertEqual(len(result.reference_images), 2)
        self.assertIn("REF_IMAGE_MISSING", self._warning_codes(result))
        skipped = [seg for seg in result.reference_segments if not seg["included"]]
        self.assertEqual(skipped[0]["mediaId"], 990)

    def test_abnormal_status_skipped(self):
        m_ok, m_bad = self._add_media(), self._add_media(status="pending")
        entity = self._character(ref_image_ids=f"[{m_ok}, {m_bad}]")
        result = self._compose(character=entity)
        self.assertEqual(len(result.reference_images), 1)
        self.assertIn("REF_IMAGE_SKIPPED", self._warning_codes(result))

    def test_min_anchor_zero_degrades(self):
        """默认 min_anchor=0：全部失效 → 降级无图不阻断（决策 #32）。"""
        entity = self._character(ref_image_ids="[990, 991]")
        result = self._compose(character=entity)
        self.assertEqual(result.reference_images, [])

    def test_min_anchor_one_blocks(self):
        """min_anchor=1：可用 0 → 执行期友好报错（决策 #32 严格模式）。"""
        self._set_param("assetMinAnchorImages", "1")
        entity = self._character(ref_image_ids="[990]")
        with self.assertRaises(AssetAnchorError):
            self._compose(character=entity)

    # --- 验收 9：渠道自适应 / role 语义 ---

    def test_multi_reference_channel(self):
        """multi_reference_image 声明、全局 N=4、5 张（第 3 张 primary）→ 4 张且 primary 第一。"""
        self._set_param("assetDefaultReferenceImages", "4")
        ids = [self._add_media() for _ in range(5)]
        entries = [
            {"id": ids[0]},
            {"id": ids[1]},
            {"id": ids[2], "role": "primary"},
            {"id": ids[3]},
            {"id": ids[4]},
        ]
        entity = self._character(ref_image_ids=json.dumps(entries))
        self._patch_channel(["image", "multi_reference_image"], "toapis")
        result = self._compose(character=entity)
        self.assertEqual(len(result.reference_images), 4)
        self.assertEqual(result.reference_images[0], self._media_url(ids[2]))
        self.assertIn("MULTI_REF_TRUNCATED", self._warning_codes(result))

    def test_single_reference_channel_takes_primary(self):
        """Poryf 单图渠道 → 注入 primary（验收 9）。"""
        ids = [self._add_media() for _ in range(3)]
        entries = [{"id": ids[0]}, {"id": ids[1], "role": "primary"}, {"id": ids[2]}]
        entity = self._character(ref_image_ids=json.dumps(entries))
        self._patch_channel(["image"], "poryf")
        result = self._compose(character=entity)
        self.assertEqual(result.reference_images, [self._media_url(ids[1])])

    def test_profile_none_single_image_fallback(self):
        """profile 未选（P2-3）：按兜底 1 张注入、无 PROFILE_MISMATCH、preferred_size 不生效。"""
        ids = [self._add_media(), self._add_media()]
        entity = self._character(
            ref_image_ids=f"[{ids[0]}, {ids[1]}]", preferred_profile_code="p1", preferred_size="1024x1024"
        )
        result = self._compose(character=entity)
        self.assertEqual(len(result.reference_images), 1)
        self.assertNotIn("PROFILE_MISMATCH", self._warning_codes(result))
        self.assertIsNone(result.effective_size)

    # --- 验收 10：token 预算与降级 ---

    def test_budget_compression_order(self):
        """超限压缩序：风格段→场景段→角色变量渲染值；身份核心句与用户正文存活（验收 10）。"""
        self._set_param("assetPromptCharBudget", "60")
        style = self._style(appearance_prompt="x" * 30)
        scene = self._scene(appearance_prompt="y" * 30)
        entity = self._character(appearance_prompt="core sentence, {{变量一}}{{变量二}}")
        result = self._compose(
            character=entity, scene=scene, style=style, variables={"变量一": "v" * 10, "变量二": "w" * 10}
        )
        self.assertNotIn("x" * 30, result.prompt)
        self.assertNotIn("y" * 30, result.prompt)
        self.assertIn("core sentence", result.prompt)
        self.assertIn("在长椅上看书", result.prompt)
        codes = self._warning_codes(result)
        self.assertIn("STYLE_DROPPED", codes)
        self.assertIn("SCENE_DROPPED", codes)

    def test_budget_char_vars_dropped_keeps_core(self):
        """角色段压缩 = 剔除变量渲染值（保留核心句）。"""
        self._set_param("assetPromptCharBudget", "30")
        entity = self._character(appearance_prompt="core, {{变量一}}")
        result = self._compose(character=entity, variables={"变量一": "v" * 40})
        self.assertIn("core", result.prompt)
        self.assertNotIn("vvvv", result.prompt)
        self.assertIn("CHARACTER_VARS_DROPPED", self._warning_codes(result))

    def test_budget_still_over_raises(self):
        """身份核心句+正文仍超限 → 报错提示缩短正文，不静默截断（验收 10）。"""
        self._set_param("assetPromptCharBudget", "10")
        entity = self._character(appearance_prompt="c" * 30)
        with self.assertRaises(AssetPromptBudgetError):
            self._compose(character=entity, user_prompt="u" * 30)

    def test_budget_negative_drop_order(self):
        """负面压缩序：风格→场景→全局→角色（角色负面最保；全局在角色前被压）。"""
        self._set_param("assetPromptCharBudget", "50")
        style = self._style(appearance_prompt="s", negative_prompt="n" * 30)
        scene = self._scene(appearance_prompt="c", negative_prompt="m" * 30)
        entity = self._character(appearance_prompt="girl", negative_prompt="bad")
        self._set_param("assetGlobalNegativePrompt", "g" * 30)
        result = self._compose(character=entity, scene=scene, style=style)
        # 全局与角色负面共存（预算 50：正文 7 + girl 4 + 30 + 1 + 分隔 ≤ 50）
        self.assertEqual(result.negative_prompt, "bad\n" + "g" * 30)
        codes = self._warning_codes(result)
        self.assertIn("NEGATIVE_STYLE_DROPPED", codes)
        self.assertIn("NEGATIVE_SCENE_DROPPED", codes)
        self.assertNotIn("NEGATIVE_GLOBAL_DROPPED", codes)

    def test_budget_exact_fit_no_compression(self):
        """恰等于预算：不触发任何压缩（P1-5 边界）。"""
        text = "z" * 10
        self._set_param("assetPromptCharBudget", str(len(text)))
        entity = self._character(appearance_prompt=text)
        result = self._compose(character=entity, user_prompt="")
        self.assertEqual(result.prompt, text)
        self.assertEqual([w for w in result.warnings if "DROPPED" in w["code"]], [])

    # --- 验收 11 + P0-1：一致性警告 / size 覆盖三分支 ---

    def test_profile_mismatch_and_size_ignored(self):
        """profile 不一致 → PROFILE_MISMATCH；用户未覆盖且渠道不匹配 → SIZE_IGNORED（验收 11）。"""
        entity = self._character(preferred_profile_code="p1", preferred_size="1024x1024")
        self._patch_channel(["image"], "poryf")
        result = self._compose(character=entity, profile_code="p2")
        codes = self._warning_codes(result)
        self.assertIn("PROFILE_MISMATCH", codes)
        self.assertIn("SIZE_IGNORED", codes)
        self.assertIsNone(result.effective_size)

    def test_user_size_overrides(self):
        """用户显式 size 最高优先且不触发 SIZE_IGNORED（P0-1）。"""
        entity = self._character(preferred_profile_code="p1", preferred_size="1024x1024")
        result = self._compose(character=entity, profile_code="p1", user_size="2048x2048")
        self.assertEqual(result.effective_size, "2048x2048")
        self.assertNotIn("SIZE_IGNORED", self._warning_codes(result))

    def test_preferred_size_applies_on_matching_profile(self):
        entity = self._character(preferred_profile_code="p1", preferred_size="1024x1024")
        result = self._compose(character=entity, profile_code="p1")
        self.assertEqual(result.effective_size, "1024x1024")
        self.assertNotIn("SIZE_IGNORED", self._warning_codes(result))

    # --- 验收 12：组装指纹 ---

    def test_fingerprint(self):
        entity = self._character(appearance_prompt="girl")
        result = self._compose(character=entity)
        # 占位断言防手滑（entity 必须参与组装才可能产生 fingerprint 变化）
        self.assertIn("girl", result.prompt)
        self.assertEqual(result.composer_version, COMPOSER_VERSION)
        expected = hashlib.sha256(
            f"{COMPOSER_VERSION}\x1f{result.prompt}\x1f{result.negative_prompt}".encode()
        ).hexdigest()[:32]
        self.assertEqual(result.composed_prompt_hash, expected)

    # --- P1-2：segments / reference_segments 拆分 ---

    def test_segments_structure(self):
        style = self._style(appearance_prompt="anime")
        entity = self._character(appearance_prompt="girl", ref_image_ids="[990]")
        result = self._compose(character=entity, style=style)
        self.assertEqual([seg["source"] for seg in result.segments], ["style", "scene", "character", "user"])
        self.assertTrue(all(set(seg) >= {"source", "text", "included"} for seg in result.segments))
        self.assertEqual(result.segments[1]["included"], False)
        self.assertEqual(result.reference_segments[0]["mediaId"], 990)
        self.assertFalse(result.reference_segments[0]["included"])

    # --- D6：合并注入（资产图在前、节点图在后、超限先裁节点图）---

    def test_extra_refs_truncated_first_when_asset_refs_fill_limit(self):
        m1, _m2 = self._add_media(), self._add_media()
        entity = self._character(ref_image_ids=f"[{m1}, {_m2}]")
        self._patch_channel(["image"], "poryf")
        result = self._compose(
            character=entity,
            extra_reference_images=["http://cdn.example.com/n1.png", "http://cdn.example.com/n2.png"],
        )
        # poryf 兜底 1 张：仅注入 1 张资产图，节点图全被裁
        self.assertEqual(result.reference_images, [self._media_url(m1)])

    def test_extra_refs_fill_remaining_slots(self):
        m1 = self._add_media()
        entity = self._character(ref_image_ids=f"[{m1}]")
        self._set_param("assetDefaultReferenceImages", "3")
        self._patch_channel(["image", "multi_reference_image"], "toapis")
        result = self._compose(
            character=entity,
            extra_reference_images=["http://cdn.example.com/n1.png", "http://cdn.example.com/n2.png"],
        )
        # 全局 N=3：资产图 1 张 + 节点图补 2 张
        self.assertEqual(
            result.reference_images,
            [self._media_url(m1), "http://cdn.example.com/n1.png", "http://cdn.example.com/n2.png"],
        )


if __name__ == "__main__":
    unittest.main()
