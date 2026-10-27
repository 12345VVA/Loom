"""限流中间件路由模板计数测试（评审 F1）。

此前 cache_key 用完整请求路径：实例级路径（/app/workflow/instances/{id}/...）与
/uploads/<uuid> 每资源一桶，遍历标识符即可线性放大计数维度，50 接口 × 120/min
实际可发 6000 req/min，限流实质失效。修复后计数桶取路由模板（限流先于路由执行，
scope["route"] 不可用，按 APIRoute.matches 自行解析），/uploads 聚合为固定单桶。

测试环境无 Redis：cache_incr 降级为进程内内存计数（cache_service 语义），
registry 绑定在 setUp 显式注册（生产由 main.py 装配期注册）。
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.framework.middleware import rate_limit as rl_mod  # noqa: E402
from app.framework.middleware.rate_limit import RateLimitMiddleware, _reset_rate_limit_caches  # noqa: E402
from app.framework.runtime import registry  # noqa: E402
from app.modules.base.service.cache_service import cache_incr  # noqa: E402


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/app/workflow/instances/{instance_id}/detail")
    def instance_detail(instance_id: int):
        return {"id": instance_id}

    @app.get("/uploads/{file_path:path}")
    def serve_upload(file_path: str):
        return {"name": file_path}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/admin/base/user/page")
    def user_page():
        return {"items": []}

    return app


class RateLimitTemplateTests(unittest.TestCase):
    """限流行为：模板同桶 / uploads 聚合 / 白名单放行 / 429 响应头 / 未匹配回退。"""

    def setUp(self) -> None:
        _reset_rate_limit_caches()
        registry.register("cache_incr", cache_incr)
        self.app = _build_app()
        self.app.add_middleware(RateLimitMiddleware)
        self.client = TestClient(self.app)
        # 每测试唯一 Bearer 令牌 → 独立 client_id：计数键互不污染
        # （cache_incr 的 Redis/内存后端都跨测试存活，同分钟窗口内同桶会串数）
        self.auth = {"Authorization": f"Bearer rl-{uuid.uuid4().hex}"}

    def _get(self, url: str):
        return self.client.get(url, headers=self.auth)

    def tearDown(self) -> None:
        _reset_rate_limit_caches()

    def _enable(self, default_limit: int = 2) -> None:
        for name, value in (
            ("RATE_LIMIT_ENABLED", True),
            ("RATE_LIMIT_DEFAULT", default_limit),
            ("RATE_LIMIT_ADMIN", default_limit),
            ("RATE_LIMIT_OPEN", default_limit),
        ):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # _PREFIX_LIMITS 首用即按当时 settings 冻结，patch 后必须强制重建
        rl_mod._PREFIX_LIMITS.clear()

    def test_instance_paths_share_template_bucket(self):
        """同模板不同实例 ID 同桶：前 2 发正常，第 3 发起（无论哪个 ID）429。"""
        self._enable(default_limit=2)
        self.assertEqual(self._get("/app/workflow/instances/1/detail").status_code, 200)
        self.assertEqual(self._get("/app/workflow/instances/2/detail").status_code, 200)
        exceeded = self._get("/app/workflow/instances/3/detail")
        self.assertEqual(exceeded.status_code, 429)
        # 修复前：每个实例 ID 独立计数，此请求应为 200
        self.assertEqual(self._get("/app/workflow/instances/999/detail").status_code, 429)

    def test_uploads_aggregated_single_bucket(self):
        """uploads 聚合为固定桶：换文件名/日期目录不放大计数维度。"""
        self._enable(default_limit=2)
        self.assertEqual(self._get("/uploads/20261027/a.png").status_code, 200)
        self.assertEqual(self._get("/uploads/20261027/b.png").status_code, 200)
        self.assertEqual(self._get("/uploads/20261028/c.png").status_code, 429)

    def test_whitelist_exact_path_bypasses(self):
        self._enable(default_limit=1)
        for _ in range(5):
            self.assertEqual(self._get("/health").status_code, 200)

    def test_429_headers(self):
        self._enable(default_limit=1)
        self._get("/app/workflow/instances/1/detail")
        exceeded = self._get("/app/workflow/instances/1/detail")
        self.assertEqual(exceeded.status_code, 429)
        self.assertEqual(exceeded.headers["Retry-After"], "60")
        self.assertEqual(exceeded.headers["X-RateLimit-Limit"], "1")
        self.assertEqual(exceeded.headers["X-RateLimit-Remaining"], "0")

    def test_admin_prefix_limit_applies_to_template(self):
        """模板保留前缀语义：/admin 桶吃 ADMIN 分级限额而非 DEFAULT。"""
        self._enable(default_limit=5)
        patcher = patch.object(settings, "RATE_LIMIT_ADMIN", 1)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(self._get("/admin/base/user/page").status_code, 200)
        self.assertEqual(self._get("/admin/base/user/page").status_code, 429)

    def test_unmatched_path_falls_back_truncated(self):
        """404 探测不崩且有计数（回退截断 path），不污染模板缓存。"""
        self._enable(default_limit=2)
        self.assertEqual(self._get("/nonexistent/xxx").status_code, 404)
        self.assertEqual(self._get("/nonexistent/yyy").status_code, 404)
        self.assertEqual(self._get("/nonexistent/zzz").status_code, 404)
        # 模板路径不受未匹配请求影响
        self.assertEqual(self._get("/app/workflow/instances/1/detail").status_code, 200)


if __name__ == "__main__":
    unittest.main()
