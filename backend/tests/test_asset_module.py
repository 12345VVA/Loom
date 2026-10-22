"""asset 模块数据层与 CRUD 骨架测试（P2）。

服务层行为用 make_test_engine 局部引擎（testing.mdc）；模块注册断言用真实 app
（EPS 出现 asset controllers、菜单清单含 asset 三菜单）。
生命周期接口（publish/fork/参考图/计数）在 P4 扩充，见 test_asset_module 同文件后续用例。
"""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, select

from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_PUBLISHED,
    AssetCharacter,
    AssetCharacterCreateRequest,
    AssetCharacterUpdateRequest,
    AssetScene,
    AssetStyle,
)
from app.modules.asset.service.character_service import AssetCharacterService
from app.modules.asset.service.reference import (
    normalize_entry_ids,
    order_entries_by_role,
    parse_ref_entries,
)
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog
from app.modules.media.model.media import MediaAsset


class _FakeUser:
    """服务层测试用的最小用户形态（is_super_admin=True 可短路角色表查询）。"""

    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin


class AssetCrudTestCase(unittest.TestCase):
    """CRUD 生命周期：draft 强制 / 编辑权限 / archived 锁 / 可见性 / code 唯一。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AssetCharacter.__table__,
                AssetScene.__table__,
                AssetStyle.__table__,
                MediaAsset.__table__,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.service = AssetCharacterService(self.session)
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.admin = _FakeUser(3, is_super_admin=True)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _create(self, code: str = "hero", current_user=None, **kwargs) -> AssetCharacter:
        payload = AssetCharacterCreateRequest(code=code, name=kwargs.pop("name", code), **kwargs)
        return self.service.add(payload, current_user=current_user or self.owner)

    def test_add_forces_draft_and_creator(self):
        """Create 请求体夹带 status/created_by 也被覆盖为 draft + 当前用户。"""
        entity = self._create()
        self.assertEqual(entity.status, ASSET_STATUS_DRAFT)
        self.assertEqual(entity.created_by, 1)

    def test_update_archived_locked(self):
        """archived 锁死编辑（验收 6）：创建者与管理员均 403。"""
        entity = self._create()
        entity.status = ASSET_STATUS_ARCHIVED
        self.session.add(entity)
        self.session.commit()

        payload = AssetCharacterUpdateRequest(id=entity.id, code="hero", name="改名")
        for user in (self.owner, self.admin):
            with self.assertRaises(HTTPException) as ctx:
                self.service.update(payload, current_user=user)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("已归档", ctx.exception.detail)

    def test_update_draft_only_creator(self):
        """draft 编辑仅创建者：他人 403、管理员对他人 draft 只读 403（验收 2/矩阵）。"""
        entity = self._create()
        payload = AssetCharacterUpdateRequest(id=entity.id, code="hero", name="改名")
        with self.assertRaises(HTTPException) as ctx:
            self.service.update(payload, current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(HTTPException) as ctx:
            self.service.update(payload, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_published_creator_or_admin(self):
        """published 编辑：创建者与管理员可，第三方 403。"""
        entity = self._create()
        entity.status = ASSET_STATUS_PUBLISHED
        self.session.add(entity)
        self.session.commit()

        self.service.update(
            AssetCharacterUpdateRequest(id=entity.id, code="hero", name="创建者改"), current_user=self.owner
        )
        self.service.update(
            AssetCharacterUpdateRequest(id=entity.id, code="hero", name="管理员改"), current_user=self.admin
        )
        with self.assertRaises(HTTPException) as ctx:
            self.service.update(
                AssetCharacterUpdateRequest(id=entity.id, code="hero", name="路人改"), current_user=self.other
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_strips_status(self):
        """update 请求体携带 status 也被剔除（状态只经迁移接口变更，P0-4）。"""
        entity = self._create()
        data = AssetCharacterUpdateRequest(id=entity.id, code="hero", name="x").model_dump()
        data["status"] = ASSET_STATUS_PUBLISHED
        updated = self.service.update(data, current_user=self.owner)
        self.assertEqual(updated.status, ASSET_STATUS_DRAFT)

    def test_code_unique_and_soft_delete_reuse(self):
        """code 唯一（400）；软删后可重建同 code（partial unique 语义）。"""
        self._create(code="hero")
        with self.assertRaises(HTTPException) as ctx:
            self._create(code="hero", current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 400)

        hero = self.session.exec(select(AssetCharacter)).first()
        self.service.delete([hero.id])
        rebuilt = self._create(code="hero", current_user=self.other)
        self.assertEqual(rebuilt.code, "hero")

    def test_code_unique_excludes_self_on_update(self):
        entity = self._create(code="hero")
        updated = self.service.update(
            AssetCharacterUpdateRequest(id=entity.id, code="hero", name="hero"), current_user=self.owner
        )
        self.assertEqual(updated.code, "hero")

    def test_visibility_filter(self):
        """管理面可见性：draft 仅创建者可见；published 全员；管理员全量（验收 2/矩阵）。"""
        self._create(code="a-draft")
        published = self._create(code="a-pub")
        published.status = ASSET_STATUS_PUBLISHED
        self.session.add(published)
        self.session.commit()
        self.service.add(AssetCharacterCreateRequest(code="b-draft", name="b"), current_user=self.other)

        mine = {row["code"] for row in self.service.list(current_user=self.owner)}
        theirs = {row["code"] for row in self.service.list(current_user=self.other)}
        admin_seen = {row["code"] for row in self.service.list(current_user=self.admin)}

        self.assertEqual(mine, {"a-draft", "a-pub"})
        self.assertEqual(theirs, {"a-pub", "b-draft"})
        self.assertEqual(admin_seen, {"a-draft", "a-pub", "b-draft"})

    def test_info_other_draft_404(self):
        """他人 draft 的 info → 404（P1-4：不可见即不存在，防存在性探测）。"""
        entity = self._create()
        with self.assertRaises(HTTPException) as ctx:
            self.service.info(entity.id, current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_transition_validation(self):
        """状态机迁移边：draft→published→archived→published；非法边 400（P0-4）。"""
        entity = self._create()
        self.assertEqual(
            self.service.transition_status(entity.id, ASSET_STATUS_PUBLISHED, self.owner).status, ASSET_STATUS_PUBLISHED
        )
        with self.assertRaises(HTTPException) as ctx:
            self.service.transition_status(entity.id, ASSET_STATUS_DRAFT, self.owner)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(
            self.service.transition_status(entity.id, ASSET_STATUS_ARCHIVED, self.owner).status, ASSET_STATUS_ARCHIVED
        )
        self.assertEqual(
            self.service.transition_status(entity.id, ASSET_STATUS_PUBLISHED, self.owner).status, ASSET_STATUS_PUBLISHED
        )
        with self.assertRaises(HTTPException) as ctx:
            self.service.transition_status(entity.id, ASSET_STATUS_ARCHIVED, self.other)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_creator_or_admin_only(self):
        """软删：创建者+管理员；第三方 403。"""
        entity = self._create()
        with self.assertRaises(HTTPException) as ctx:
            self.service.delete([entity.id], current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)
        self.service.delete([entity.id], current_user=self.admin)

    def test_missing_media_ids_annotation(self):
        """出口增强：ref_image_ids 中悬空 media id → missingMediaIds（详情失效标注数据源）。"""
        media = MediaAsset(asset_type="image", status="success", md5="a" * 32)
        self.session.add(media)
        self.session.commit()
        entity = self._create(ref_image_ids=f'[{{"id": {media.id}}}, {{"id": 990}}, 991]')
        data = self.service.info(entity.id, current_user=self.owner)
        self.assertEqual(data["missingMediaIds"], [990, 991])


class RefEntriesTestCase(unittest.TestCase):
    """参考图 JSON 契约解析（决策 #28：双形态兼容）。"""

    def test_structured_entries(self):
        entries = parse_ref_entries('[{"id": 1, "role": "primary"}, {"id": 2}]')
        self.assertEqual(entries, [{"id": 1, "role": "primary"}, {"id": 2}])

    def test_legacy_plain_id_array(self):
        self.assertEqual(parse_ref_entries("[1, 2, 3]"), [{"id": 1}, {"id": 2}, {"id": 3}])

    def test_bad_json_returns_empty(self):
        self.assertEqual(parse_ref_entries("not-json"), [])
        self.assertEqual(parse_ref_entries(None), [])

    def test_order_by_role(self):
        """primary 固定第一顺位；无标记按原序（首位天然 primary 语义）。"""
        entries = [{"id": 1}, {"id": 2, "role": "primary"}, {"id": 3}]
        self.assertEqual(normalize_entry_ids(entries), [2, 1, 3])
        self.assertEqual(normalize_entry_ids([{"id": 7}, {"id": 8}]), [7, 8])

    def test_order_entries_by_role_keeps_rest_order(self):
        entries = [{"id": 4}, {"id": 5}, {"id": 6, "role": "primary"}]
        self.assertEqual(order_entries_by_role(entries), [{"id": 6, "role": "primary"}, {"id": 4}, {"id": 5}])


class ReferenceWriteTestCase(unittest.TestCase):
    """参考图集写操作：MD5 防重 / role 校验 / 上限 / 重排校验。"""

    def setUp(self):
        self.engine = make_test_engine(tables=[AssetCharacter.__table__, MediaAsset.__table__])
        self.session = Session(self.engine)
        self.service = AssetCharacterService(self.session)
        self.owner = _FakeUser(1)
        from app.modules.asset.service.reference import ReferenceService

        self.ref_service = ReferenceService(self.session, self.service)
        self.entity = self.service.add(AssetCharacterCreateRequest(code="hero", name="hero"), current_user=self.owner)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _add_media(self, md5: str | None = None) -> int:
        media = MediaAsset(asset_type="image", status="success", md5=md5)
        self.session.add(media)
        self.session.commit()
        self.session.refresh(media)
        return media.id

    def test_add_and_md5_dedup(self):
        """同 md5 已在集中 → 幂等返回不重复追加（需求 4.3）。"""
        mid = self._add_media(md5="m1")
        result = self.ref_service.add_reference(self.entity.id, mid, None, self.owner)
        self.assertEqual(len(result["referenceImages"]), 1)

        duplicate = MediaAsset(asset_type="image", status="success", md5="m1")
        self.session.add(duplicate)
        self.session.commit()
        self.session.refresh(duplicate)
        result = self.ref_service.add_reference(self.entity.id, duplicate.id, None, self.owner)
        self.assertEqual(len(result["referenceImages"]), 1)

    def test_add_requires_editable(self):
        """archived 期间参考图写锁死（写权限=编辑权限）。"""
        mid = self._add_media()
        self.entity.status = ASSET_STATUS_ARCHIVED
        self.session.add(self.entity)
        self.session.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.ref_service.add_reference(self.entity.id, mid, None, self.owner)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_role_validation_and_media_missing(self):
        mid = self._add_media()
        with self.assertRaises(HTTPException) as ctx:
            self.ref_service.add_reference(self.entity.id, mid, "angle", self.owner)
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(HTTPException) as ctx:
            self.ref_service.add_reference(self.entity.id, 99999, None, self.owner)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_remove_and_reorder(self):
        m1, m2, m3 = self._add_media(), self._add_media(), self._add_media()
        self.ref_service.add_reference(self.entity.id, m1, "primary", self.owner)
        self.ref_service.add_reference(self.entity.id, m2, None, self.owner)
        self.ref_service.add_reference(self.entity.id, m3, None, self.owner)

        result = self.ref_service.reorder_references(self.entity.id, [m3, m1, m2], self.owner)
        self.assertEqual([entry["id"] for entry in result["referenceImages"]], [m3, m1, m2])

        result = self.ref_service.remove_reference(self.entity.id, m3, self.owner)
        self.assertEqual([entry["id"] for entry in result["referenceImages"]], [m1, m2])

        with self.assertRaises(HTTPException) as ctx:
            self.ref_service.reorder_references(self.entity.id, [m1], self.owner)
        self.assertEqual(ctx.exception.status_code, 400)


class ForkAndStatsTestCase(unittest.TestCase):
    """fork 复制副本（验收 15）+ 引用计数第一阶段口径（验收 13）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AssetCharacter.__table__,
                MediaAsset.__table__,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.service = AssetCharacterService(self.session)
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_fork_published_only(self):
        """仅 published 可复制；draft/archived 拒绝（决策 #22）。"""
        from fastapi import HTTPException as _HE

        draft = self.service.add(AssetCharacterCreateRequest(code="hero", name="小白"), current_user=self.owner)
        with self.assertRaises(_HE) as ctx:
            self.service.fork(draft.id, current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_fork_creates_own_draft_with_refs(self):
        """副本归属复制者、code 加后缀不冲突、参考图关系保留（验收 15）。"""
        media = MediaAsset(asset_type="image", status="success", storage_url="/uploads/test/a.png")
        self.session.add(media)
        self.session.commit()
        entity = self.service.add(AssetCharacterCreateRequest(code="hero", name="小白"), current_user=self.owner)
        entity.status = ASSET_STATUS_PUBLISHED
        entity.ref_image_ids = f'[{{"id": {media.id}, "role": "primary"}}]'
        self.session.add(entity)
        self.session.commit()

        copy = self.service.fork(entity.id, current_user=self.other)
        self.assertEqual(copy.status, ASSET_STATUS_DRAFT)
        self.assertEqual(copy.created_by, 2)
        self.assertNotEqual(copy.code, "hero")
        self.assertTrue(copy.code.startswith("hero-f"))
        self.assertEqual(parse_ref_entries(copy.ref_image_ids), [{"id": media.id, "role": "primary"}])

    def test_reference_stats_task_dedup(self):
        """成功产出数按任务去重：同任务多产物计 1；failed 不计（验收 13）。"""
        media = MediaAsset(asset_type="image", status="success", storage_url="/uploads/test/a.png")
        self.session.add(media)
        self.session.commit()
        entity = self.service.add(AssetCharacterCreateRequest(code="hero", name="小白"), current_user=self.owner)
        entity.status = ASSET_STATUS_PUBLISHED
        self.session.add(entity)
        self.session.commit()

        for task_id in (101, 101, 202):
            self.session.add(
                MediaAsset(
                    asset_type="image",
                    status="success",
                    source_character_id=entity.id,
                    source_task_id=task_id,
                    storage_url=f"/uploads/test/{task_id}.png",
                )
            )
        self.session.add(
            MediaAsset(
                asset_type="image",
                status="failed",
                source_character_id=entity.id,
                source_task_id=303,
            )
        )
        self.session.commit()

        stats = self.service.reference_stats(entity.id)
        self.assertEqual(stats["successCount"], 2)  # 任务 101/202 各计 1，failed 不计

    def test_reference_stats_empty(self):
        stats = self.service.reference_stats(
            self.service.add(AssetCharacterCreateRequest(code="empty", name="x"), current_user=self.owner).id
        )
        self.assertEqual(stats["successCount"], 0)
        self.assertIsNone(stats["lastProducedAt"])


class ModuleRegistrationTestCase(unittest.TestCase):
    """模块注册断言：EPS 出现 asset controllers；菜单清单含 asset 三菜单。"""

    def setUp(self):
        from fastapi.testclient import TestClient

        from main import app

        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_eps_contains_asset_controllers(self):
        response = self.client.get("/admin/base/open/eps")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("asset", data)
        prefixes = {item["prefix"] for item in data["asset"]}
        for expected in ("/admin/asset/character", "/admin/asset/scene", "/admin/asset/style"):
            self.assertIn(expected, prefixes)

    def test_menu_manifest_contains_asset_menus(self):
        from app.modules.loader import load_menu_manifest_items

        items = load_menu_manifest_items()
        routers = {item.path for item in items if getattr(item, "path", None)}
        for expected in ("/asset/character", "/asset/scene", "/asset/style"):
            self.assertIn(expected, routers)


if __name__ == "__main__":
    unittest.main()
