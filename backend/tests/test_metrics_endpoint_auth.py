"""/metrics 端点令牌鉴权测试（评审 F4）。

端点暴露全站接口清单、调用量与延迟，令牌 fail-closed：未配置 METRICS_TOKEN 时
即使 METRICS_ENABLED=True 也恒 404（与禁用同响应，不暴露端点存在）；配置后须带
Authorization: Bearer <token>（恒时比较）。测试直接打 main.app 的真实端点
（导入期副作用为既有测试接受的形态，见 test_middleware_topology.py），
不进 lifespan 上下文（不触 init_db）。
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.startup_checks import validate_startup_settings  # noqa: E402

_DISABLED_MARK = "# metrics disabled"


class MetricsEndpointAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_disabled_remains_disabled(self):
        with (
            patch.object(settings, "METRICS_ENABLED", False),
            patch.object(settings, "METRICS_TOKEN", "s3cret"),
        ):
            resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(_DISABLED_MARK, resp.text)

    def test_enabled_without_token_fail_closed(self):
        """开了开关但未配置令牌：恒 404，不暴露指标也不暴露端点存在性。"""
        with (
            patch.object(settings, "METRICS_ENABLED", True),
            patch.object(settings, "METRICS_TOKEN", ""),
        ):
            resp = self.client.get("/metrics")
        self.assertIn(_DISABLED_MARK, resp.text)

    def test_enabled_with_token_requires_bearer(self):
        with (
            patch.object(settings, "METRICS_ENABLED", True),
            patch.object(settings, "METRICS_TOKEN", "s3cret"),
        ):
            anonymous = self.client.get("/metrics")
            wrong = self.client.get("/metrics", headers={"Authorization": "Bearer wrong"})
            ok = self.client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
            via_query = self.client.get("/metrics", params={"token": "s3cret"})
        self.assertIn(_DISABLED_MARK, anonymous.text)
        self.assertIn(_DISABLED_MARK, wrong.text)
        self.assertEqual(ok.status_code, 200)
        self.assertIn("loom_http_requests_total", ok.text)
        self.assertEqual(via_query.status_code, 200)

    def test_token_compare_is_constant_time_safe(self):
        """超长攻击串不报错、不通过（secrets.compare_digest 对不同长度直接不等）。"""
        with (
            patch.object(settings, "METRICS_ENABLED", True),
            patch.object(settings, "METRICS_TOKEN", "s3cret"),
        ):
            resp = self.client.get("/metrics", headers={"Authorization": "Bearer " + "a" * 5000})
        self.assertIn(_DISABLED_MARK, resp.text)


class MetricsTokenStartupCheckTests(unittest.TestCase):
    def test_enabled_without_token_reports_warning(self):
        config = settings.model_copy(update={"METRICS_ENABLED": True, "METRICS_TOKEN": ""})
        results = validate_startup_settings(config)
        matched = [item for item in results if item.key == "METRICS_TOKEN"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].level, "warning")

    def test_enabled_with_token_no_warning(self):
        config = settings.model_copy(update={"METRICS_ENABLED": True, "METRICS_TOKEN": "s3cret"})
        self.assertNotIn("METRICS_TOKEN", {item.key for item in validate_startup_settings(config)})


if __name__ == "__main__":
    unittest.main()
