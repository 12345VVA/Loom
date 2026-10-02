"""百炼业务空间模型自动拉取测试。

覆盖：
1. 前置校验：workspace_id / API Key 缺失的可读提示
2. 分页拉取合并与字段映射，inference=false 保守过滤
3. 业务错误（success=false）透出 code/message/request_id
4. sync_models 集成：新模型停用待人工分类
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.core.secret import encrypt_secret
from app.modules.ai.model.ai import AiModel, AiProvider
from app.modules.ai.service.adapters.bailian_openapi import list_workspace_authorized_models
from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.ai.service.adapters.factory import BailianAdapter
from app.modules.ai.service.provider_service import AiProviderService


def _page_response(items: list[dict], total: int, page_no: int = 1) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "code": None,
        "message": None,
        "success": True,
        "request_id": "req-1",
        "output": {"total": total, "page_no": page_no, "page_size": 200, "permissions": items},
    }
    return response


def _permission(model: str, name: str, *, inference: bool = True) -> dict:
    return {"model": model, "name": name, "permissions": {"inference": inference, "fine_tune": False, "deploy": False}}


def _make_provider(extra_config: str | None, *, with_api_key: bool = True) -> AiProvider:
    return BailianAdapter(
        AiProvider(
            code="bailian",
            name="阿里百炼",
            adapter="bailian",
            extra_config=extra_config,
            api_key_cipher=encrypt_secret("sk-test") if with_api_key else None,
        )
    )


class BailianListModelsTest(unittest.TestCase):
    def test_requires_workspace_id(self):
        """未配置 workspace_id 时给出可读提示"""
        adapter = _make_provider('{"timeout": 60}')
        with self.assertRaises(UpstreamApiError) as ctx:
            adapter.list_models()
        self.assertIn("workspace_id", str(ctx.exception))

    def test_requires_workspace_id_when_extra_config_empty(self):
        adapter = _make_provider(None)
        with self.assertRaises(UpstreamApiError) as ctx:
            adapter.list_models()
        self.assertIn("workspace_id", str(ctx.exception))

    def test_requires_api_key(self):
        adapter = _make_provider('{"workspace_id": "ws-1"}', with_api_key=False)
        with self.assertRaises(UpstreamApiError) as ctx:
            adapter.list_models()
        self.assertIn("API Key", str(ctx.exception))

    def test_merges_pages_and_maps_fields(self):
        """分页循环拉全，model→code、name→name"""
        responses = [
            _page_response(
                [_permission("qwen-plus", "通义千问-Plus"), _permission("qwen-turbo", "通义千问-Turbo")],
                total=3,
                page_no=1,
            ),
            _page_response([_permission("qwen3-max", "通义千问3-Max")], total=3, page_no=2),
        ]
        with patch("app.modules.ai.service.adapters.bailian_openapi.httpx.get", side_effect=responses) as mock_get:
            models = list_workspace_authorized_models(api_key="sk-test", workspace_id="ws-1")
        self.assertEqual([m["code"] for m in models], ["qwen-plus", "qwen-turbo", "qwen3-max"])
        self.assertEqual(models[0]["name"], "通义千问-Plus")
        # 端点按业务空间分子域，且拉取已授权可推理模型
        first_call = mock_get.call_args_list[0]
        self.assertIn("ws-1.cn-beijing.maas.aliyuncs.com", first_call.args[0])
        self.assertEqual(first_call.kwargs["params"]["authorization_scope"], "AUTHORIZED")
        self.assertEqual(first_call.kwargs["params"]["action"], "INFERENCE")
        self.assertEqual(first_call.kwargs["headers"]["Authorization"], "Bearer sk-test")

    def test_filters_non_inference_permissions(self):
        """inference=false 的条目不入库（无调用权限的授权项）"""
        responses = [
            _page_response(
                [_permission("qwen-plus", "通义千问-Plus"), _permission("qwen-ft", "可训练不可调用", inference=False)],
                total=2,
            )
        ]
        with patch("app.modules.ai.service.adapters.bailian_openapi.httpx.get", side_effect=responses):
            models = list_workspace_authorized_models(api_key="sk-test", workspace_id="ws-1")
        self.assertEqual([m["code"] for m in models], ["qwen-plus"])

    def test_business_error_raises_with_request_id(self):
        """success=false 透出 code/message/request_id"""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "code": "InvalidApiKey",
            "message": "API key 无效",
            "success": False,
            "request_id": "req-err-1",
        }
        with patch("app.modules.ai.service.adapters.bailian_openapi.httpx.get", return_value=response):
            with self.assertRaises(UpstreamApiError) as ctx:
                list_workspace_authorized_models(api_key="bad", workspace_id="ws-1")
        self.assertIn("InvalidApiKey", str(ctx.exception))
        self.assertEqual(ctx.exception.request_id, "req-err-1")


class BailianSyncModelsTest(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.provider = AiProvider(
            code="bailian",
            name="阿里百炼",
            adapter="bailian",
            extra_config='{"workspace_id": "ws-1"}',
            api_key_cipher=encrypt_secret("sk-test"),
        )
        self.session.add(self.provider)
        self.session.commit()
        self.session.refresh(self.provider)

    def tearDown(self):
        self.session.close()

    def test_sync_creates_pending_models(self):
        """同步入库：新模型停用待人工分类，无价格信息"""
        with patch(
            "app.modules.ai.service.adapters.factory.list_workspace_authorized_models",
            return_value=[{"code": "qwen-plus", "name": "通义千问-Plus"}],
        ):
            result = AiProviderService(self.session).sync_models(self.provider.id)
        self.assertEqual(result["created"], 1)
        row = self.session.query(AiModel).filter(AiModel.code == "qwen-plus").one()
        self.assertFalse(row.is_active)
        self.assertIn("sync-pending", row.capabilities or "")
        self.assertIsNone(row.pricing_config)


if __name__ == "__main__":
    unittest.main()
