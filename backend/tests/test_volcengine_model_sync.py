"""火山方舟可用模型自动拉取测试。

覆盖：
1. 火山 V4 签名：确定性、Authorization 结构、query 排序
2. iter_ark_available_models：分页合并与字段映射
3. VolcengineArkAdapter.list_models：AK/SK 缺失提示
4. sync_models：新模型停用待分类 + pricing 入库；已存在模型不动 is_active
5. provider 管理侧 AK/SK：加密落库、掩码、读取不泄漏密文
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.secret import encrypt_secret
from app.modules.ai.model.ai import AiModel, AiProvider, AiProviderUpdateRequest
from app.modules.ai.service.adapters.factory import VolcengineArkAdapter
from app.modules.ai.service.adapters.volcengine_openapi import (
    iter_ark_available_models,
    sign_volcengine_v4,
)
from app.modules.ai.service.provider_service import AiProviderService
from app.modules.base.service.admin_service import BaseAdminCrudService


def _openapi_page(items: list[dict], total: int) -> dict:
    return {"Items": items, "PageNumber": 1, "TotalCount": total}


def _ark_item(name: str, display: str | None = None) -> dict:
    return {
        "FoundationModelName": name,
        "DisplayName": display or name,
        "State": "Available",
        "VendorName": "doubao",
        "IsDeprecated": False,
        "IsLimitedActivation": False,
        "ChargeItems": [{"Price": 0.0032, "Type": "basic", "UnitCode": "per_1k_tokens"}],
    }


class VolcengineSignatureTest(unittest.TestCase):
    def test_signature_is_deterministic_and_well_formed(self):
        """同一输入签名稳定，且 Authorization 结构符合火山 V4 规范"""
        kwargs = dict(
            method="POST",
            host="ark.cn-beijing.volcengineapi.com",
            path="/",
            query={"Version": "2024-01-01", "Action": "ListModelActivations"},
            body='{"a":1}',
            access_key="AKLTtest",
            secret_key="SKtest",
            now=__import__("datetime").datetime(2026, 9, 20, 3, 0, 0, tzinfo=__import__("datetime").timezone.utc),
        )
        headers = sign_volcengine_v4(**kwargs)
        again = sign_volcengine_v4(**kwargs)
        self.assertEqual(headers, again)

        self.assertEqual(headers["X-Date"], "20260920T030000Z")
        auth = headers["Authorization"]
        self.assertTrue(auth.startswith("HMAC-SHA256 Credential=AKLTtest/"))
        self.assertIn("/20260920/cn-beijing/ark/request,", auth)
        # SignedHeaders 须按字母序：content-type;host;x-content-sha256;x-date
        self.assertIn("SignedHeaders=content-type;host;x-content-sha256;x-date,", auth)
        self.assertIn("Signature=", auth)
        # X-Content-Sha256 与 body 哈希一致
        import hashlib

        self.assertEqual(headers["X-Content-Sha256"], hashlib.sha256(b'{"a":1}').hexdigest())

    def test_iter_models_merges_pages_and_maps_fields(self):
        """分页循环拉全并映射为统一结构，计费信息原样透出"""
        responses = [
            _openapi_page([_ark_item("doubao-seed-1-6"), _ark_item("doubao-embedding")], total=3),
            _openapi_page([_ark_item("doubao-seedream-4-5-251128", "Doubao Seedream 4.5")], total=3),
        ]
        with patch(
            "app.modules.ai.service.adapters.volcengine_openapi.list_model_activations",
            side_effect=responses,
        ):
            models = iter_ark_available_models(access_key="ak", secret_key="sk")
        self.assertEqual([m["code"] for m in models], ["doubao-seed-1-6", "doubao-embedding", "doubao-seedream-4-5-251128"])
        self.assertEqual(models[0]["state"], "Available")
        self.assertEqual(models[0]["pricing"]["ChargeItems"][0]["Price"], 0.0032)
        self.assertFalse(models[0]["deprecated"])


class VolcengineAdapterListModelsTest(unittest.TestCase):
    def _adapter(self, provider: AiProvider) -> VolcengineArkAdapter:
        return VolcengineArkAdapter(provider)

    def test_list_models_requires_admin_keys(self):
        """未配置管理 AK/SK 时给出可读提示而非 OpenAI /models 404"""
        provider = AiProvider(code="volcengine-ark", name="火山方舟", adapter="volcengine-ark")
        with self.assertRaises(RuntimeError) as ctx:
            self._adapter(provider).list_models()
        self.assertIn("Access Key", str(ctx.exception))

    def test_list_models_uses_admin_keys(self):
        provider = AiProvider(
            code="volcengine-ark",
            name="火山方舟",
            adapter="volcengine-ark",
            admin_access_key_cipher=encrypt_secret("ak"),
            admin_secret_key_cipher=encrypt_secret("sk"),
        )
        with patch(
            "app.modules.ai.service.adapters.factory.iter_ark_available_models",
            return_value=[{"code": "doubao-seed-1-6", "name": "Doubao Seed 1.6"}],
        ) as mock_iter:
            models = self._adapter(provider).list_models()
        self.assertEqual(models[0]["code"], "doubao-seed-1-6")
        self.assertEqual(mock_iter.call_args.kwargs["access_key"], "ak")
        self.assertEqual(mock_iter.call_args.kwargs["secret_key"], "sk")


class SyncModelsUpsertTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        # list_models 前置校验管理 AK/SK，测试厂商需配好密文使 patch 点可达
        self.provider = AiProvider(
            code="volcengine-ark",
            name="火山方舟",
            adapter="volcengine-ark",
            admin_access_key_cipher=encrypt_secret("ak"),
            admin_secret_key_cipher=encrypt_secret("sk"),
        )
        self.session.add(self.provider)
        self.session.commit()
        self.session.refresh(self.provider)

    def tearDown(self):
        self.session.close()

    def _sync(self, models: list[dict]) -> dict:
        with patch("app.modules.ai.service.adapters.factory.iter_ark_available_models", return_value=models):
            return AiProviderService(self.session).sync_models(self.provider.id)

    def test_new_models_pending_and_pricing_saved(self):
        """新拉取模型置停用待人工分类，计费信息写入 pricing_config"""
        result = self._sync(
            [
                {
                    "code": "doubao-seedream-4-5-251128",
                    "name": "Doubao Seedream 4.5",
                    "pricing": {"ChargeItems": [{"Price": 0.0032}]},
                },
                {"code": "doubao-seed-1-6", "name": "Doubao Seed 1.6", "pricing": None},
            ]
        )
        self.assertEqual(result["created"], 2)
        rows = self.session.query(AiModel).order_by(AiModel.code).all()
        by_code = {row.code: row for row in rows}
        self.assertFalse(by_code["doubao-seed-1-6"].is_active)
        self.assertIn("sync-pending", by_code["doubao-seed-1-6"].capabilities or "")
        self.assertIsNone(by_code["doubao-seed-1-6"].pricing_config)
        self.assertEqual(
            json.loads(by_code["doubao-seedream-4-5-251128"].pricing_config)["ChargeItems"][0]["Price"], 0.0032
        )

    def test_existing_models_keep_active_state(self):
        """已存在模型（管理员手动启用）同步后仍保持启用，仅补元数据"""
        self._sync([{"code": "doubao-seed-1-6", "name": "Doubao Seed 1.6", "pricing": None}])
        row = self.session.query(AiModel).filter(AiModel.code == "doubao-seed-1-6").one()
        row.is_active = True
        row.model_type = "chat"
        self.session.add(row)
        self.session.commit()

        result = self._sync(
            [
                {
                    "code": "doubao-seed-1-6",
                    "name": "Doubao Seed 1.6 Updated",
                    "pricing": {"ChargeItems": [{"Price": 0.002}]},
                }
            ]
        )
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.session.refresh(row)
        self.assertTrue(row.is_active)
        self.assertEqual(row.name, "Doubao Seed 1.6 Updated")
        self.assertEqual(json.loads(row.pricing_config)["ChargeItems"][0]["Price"], 0.002)


class ProviderAdminKeyStorageTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.service = AiProviderService(self.session)

    def tearDown(self):
        self.session.close()

    def test_add_encrypts_admin_keys_and_masks_access_key(self):
        """AK/SK 加密落库，AK 留掩码，返回数据不泄漏密文"""
        result = self.service.add(
            {
                "code": "volcengine-ark",
                "name": "火山方舟",
                "adapter": "volcengine-ark",
                "admin_access_key": "AKLT1111222233334444",
                "admin_secret_key": "SKsecretvalue",
            }
        )
        self.assertEqual(result["adminAccessKeyMask"], "AKLT****4444")
        self.assertTrue(result["hasAdminAccessKey"])
        self.assertTrue(result["hasAdminSecretKey"])
        entity = self.session.get(AiProvider, result["id"])
        self.assertIsNotNone(entity.admin_access_key_cipher)
        self.assertIsNotNone(entity.admin_secret_key_cipher)
        self.assertNotIn("SKsecretvalue", entity.admin_secret_key_cipher)
        # 读路径不回传密文（finalize 后为 camelCase 键）
        self.assertIsNone(result.get("adminAccessKeyCipher"))
        self.assertIsNone(result.get("adminSecretKeyCipher"))

    def test_update_keeps_keys_when_blank(self):
        """AK/SK 留空表示不修改，不覆盖已存密文"""
        result = self.service.add(
            {
                "code": "volcengine-ark",
                "name": "火山方舟",
                "adapter": "volcengine-ark",
                "admin_access_key": "AKLT1111222233334444",
                "admin_secret_key": "SKsecretvalue",
            }
        )
        entity = self.session.get(AiProvider, result["id"])
        cipher_before = entity.admin_secret_key_cipher
        self.service.update(
            AiProviderUpdateRequest(
                id=entity.id,
                name="火山方舟2",
                admin_access_key="",
                admin_secret_key="",
            )
        )
        self.session.refresh(entity)
        self.assertEqual(entity.admin_secret_key_cipher, cipher_before)
        self.assertEqual(entity.admin_access_key_mask, "AKLT****4444")
        self.assertEqual(entity.name, "火山方舟2")


class FinalizeAliasTest(unittest.TestCase):
    def test_admin_access_key_mask_alias_resolved(self):
        """finalize 出口把 admin_access_key_mask 转 camelCase 供前端列表展示"""
        svc = BaseAdminCrudService.__new__(BaseAdminCrudService)
        data = svc._finalize_data({"admin_access_key_mask": "AKLT****4444"})
        self.assertEqual(data.get("adminAccessKeyMask"), "AKLT****4444")


if __name__ == "__main__":
    unittest.main()
