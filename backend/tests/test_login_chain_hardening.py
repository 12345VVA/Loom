"""登录链路 R 系列修复回归（专项 §14 → §15）。

- R3：成功登录只清账号维度失败计数，IP 维度保留（原任意成功登录清零整台 IP 风控状态）
- R5：SSO 开启时缓存基线缺失 fail-closed（原静默把当前 token 扶正为新基线）
- R7：refresh 重用检测——重放上一代 token 整族作废（原仅静默 401，无泄露告警）
- R10：access 校验补 sid 会话存活——踢出/登出后历史轮转 access token 一并失效
"""

from __future__ import annotations

import os
import sys
import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session as DbSession
from sqlmodel import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.modules.base.model.auth import User  # noqa: E402
from app.modules.base.service.auth_service import AuthService  # noqa: E402
from app.modules.base.service.authority_service import (  # noqa: E402
    build_token_cache_key,
    build_token_version_cache_key,
    delete_session,
    get_user_from_access_token,
    refresh_session,
    register_session,
)
from app.modules.base.service.cache_service import cache_delete, cache_get  # noqa: E402
from app.modules.base.service.security_service import create_access_token  # noqa: E402
from main import app  # noqa: E402


def _admin_user() -> User:
    with DbSession(engine) as s:
        admin = s.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
        assert admin is not None
        return admin


class LoginChainHardeningTests(unittest.TestCase):
    """R3/R5/R7/R10 回归。R10/R5 为 service 级直调（R10 的洞在服务函数内部，HTTP 隔离不出历史代 token）。"""

    @classmethod
    def setUpClass(cls):
        # lifespan（init_db/bootstrap）每类只跑一次（测试时长优化先例）
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        # 关闭验证码，聚焦登录链路逻辑（DEBUG=True 时 captcha_enabled 由本开关决定）
        self._old_captcha = settings.ADMIN_CAPTCHA_ENABLED
        settings.ADMIN_CAPTCHA_ENABLED = False
        self.client.cookies.clear()

    def tearDown(self):
        settings.ADMIN_CAPTCHA_ENABLED = self._old_captcha
        # 清理探针残留，避免跨文件 IP/账号风控串扰（限流 429 教训）
        cache_delete(
            AuthService._build_ip_fail_key("testclient"),
            AuthService._build_ip_lock_key("testclient"),
            AuthService._build_account_fail_key(settings.DEFAULT_ADMIN_USERNAME),
            AuthService._build_account_lock_key(settings.DEFAULT_ADMIN_USERNAME),
        )

    def _login(self) -> dict:
        res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["data"]

    def test_r3_success_login_keeps_ip_fail_counter(self):
        """成功登录清账号计数、保留 IP 计数（原实现连 IP 计数/锁一起删 → R3）。"""
        service = object.__new__(AuthService)
        service._mark_login_failure(settings.DEFAULT_ADMIN_USERNAME, "testclient")
        ip_key = AuthService._build_ip_fail_key("testclient")
        account_key = AuthService._build_account_fail_key(settings.DEFAULT_ADMIN_USERNAME)
        ip_before = cache_get(ip_key)
        self.assertEqual(ip_before, "1")

        self._login()

        # 账号维度被清、IP 维度保留——持有有效账号者无法再借登录重置整台 IP 风控状态
        self.assertIsNone(cache_get(account_key))
        self.assertEqual(cache_get(ip_key), ip_before)

    def test_r7_refresh_reuse_kills_token_family(self):
        """重放上一代 refresh token → 401 且整族作废（token_version 递增）。"""
        login_res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
            },
        )
        self.assertEqual(login_res.status_code, 200, login_res.text)
        # refresh_token 仅走 HttpOnly cookie，响应体不回传（防 XSS 凭证失窃）
        refresh1 = login_res.cookies.get("refresh_token")
        self.assertTrue(refresh1)
        version_key = build_token_version_cache_key(_admin_user().id)
        version_before = int(cache_get(version_key) or 0)

        # 正常轮转一次：R1 → R2
        first = self.client.post("/admin/base/open/refreshToken", json={})
        self.assertEqual(first.status_code, 200, first.text)
        refresh2 = first.cookies.get("refresh_token")
        self.assertTrue(refresh2)

        # 重放 R1（先清 cookie，确保走 body 的旧值而非新 cookie）
        self.client.cookies.clear()
        replay = self.client.post("/admin/base/open/refreshToken", json={"refreshToken": refresh1})
        self.assertEqual(replay.status_code, 401)

        # 家族已作废：token_version 递增，最新代 R2 也必须失效
        version_after = int(cache_get(version_key) or 0)
        self.assertGreater(version_after, version_before, "重放上一代 refresh 未触发整族作废（R7）")
        self.client.cookies.clear()
        second = self.client.post("/admin/base/open/refreshToken", json={"refreshToken": refresh2})
        self.assertEqual(second.status_code, 401)

    def test_r10_session_deletion_kills_rotated_access_tokens(self):
        """踢出/登出（会话删除）后，历史上轮转产生的旧代 access token 一并失效（R10）。"""
        admin = _admin_user()

        register_session(admin.id, "sid-r10", "refresh-r1", "jti-r1")
        token1 = create_access_token(admin, "sid-r10")
        with DbSession(engine) as db:
            user, _ = get_user_from_access_token(db, token1)
            self.assertEqual(user.id, admin.id)

        # 轮转：会话记录的 access_jti 被覆盖为 jti-r2，旧代 jti-r1 无处登记（无从拉黑）
        refresh_session(admin.id, "sid-r10", "refresh-r2", "jti-r2")

        # 踢出/登出 = 删除会话记录：历史代 token1 原本仍可用至自身 TTL，修复后随会话一并失效
        delete_session(admin.id, "sid-r10")
        with DbSession(engine) as db:
            with self.assertRaises(HTTPException) as ctx:
                get_user_from_access_token(db, token1)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_r5_sso_enabled_rejects_missing_baseline(self):
        """SSO 开启且 token 基线缓存缺失 → 401 fail-closed（原静默扶正为新基线，R5）。"""
        admin = _admin_user()
        old_sso = settings.ADMIN_SSO_ENABLED
        settings.ADMIN_SSO_ENABLED = True
        try:
            register_session(admin.id, "sid-r5", "refresh-r5", "jti-r5")
            # 确保基线缺失（模拟缓存到期/清理/重启）
            cache_delete(build_token_cache_key(admin.id))
            token = create_access_token(admin, "sid-r5")
            with DbSession(engine) as db:
                with self.assertRaises(HTTPException) as ctx:
                    get_user_from_access_token(db, token)
                self.assertEqual(ctx.exception.status_code, 401)
                self.assertIn("其他位置", str(ctx.exception.detail))
        finally:
            settings.ADMIN_SSO_ENABLED = old_sso
            delete_session(admin.id, "sid-r5")


if __name__ == "__main__":
    unittest.main()
