"""多设备会话管理测试。

覆盖：
- 多设备登录并存（修复"后登踢前登"）
- 退出仅当前设备（不影响其他设备 access/refresh）
- 设备管理页踢出指定会话
- 各设备 refresh 独立
- 会话列表正确标记当前设备
- clear_user_sessions 清空全部（改密码踢全部的底层机制）
"""

import os
import sys
import unittest

from fastapi.testclient import TestClient
from sqlmodel import Session as DbSession, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.modules.base.model.auth import User  # noqa: E402
from app.modules.base.service.authority_service import (  # noqa: E402
    clear_user_sessions,
    get_session,
    register_session,
)
from main import app  # noqa: E402


def _login_body() -> dict:
    return {
        "username": settings.DEFAULT_ADMIN_USERNAME,
        "password": settings.DEFAULT_ADMIN_PASSWORD,
    }


def _admin_user_id() -> int | None:
    with DbSession(engine) as s:
        admin = s.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
        return admin.id if admin else None


class SessionManagementTests(unittest.TestCase):
    """多设备会话：登录并存 / 退出仅当前 / 踢出指定 / 各自刷新 / 列表标记。"""

    def setUp(self):
        # 关闭验证码，聚焦会话逻辑（DEBUG=True 时 captcha_enabled 由本开关决定）
        self._old_captcha = settings.ADMIN_CAPTCHA_ENABLED
        settings.ADMIN_CAPTCHA_ENABLED = False
        # 清理 admin 残留会话，保证 total 断言稳定
        admin_id = _admin_user_id()
        if admin_id:
            clear_user_sessions(admin_id)
        # 不同 X-Device-Id 模拟两台不同设备（后端按 device_id 聚合）
        self.client_a = TestClient(app, headers={"X-Device-Id": "device-a"})
        self.client_b = TestClient(app, headers={"X-Device-Id": "device-b"})
        self.client_a.__enter__()
        self.client_b.__enter__()

    def tearDown(self):
        self.client_a.__exit__(None, None, None)
        self.client_b.__exit__(None, None, None)
        settings.ADMIN_CAPTCHA_ENABLED = self._old_captcha

    def _login(self, client: TestClient) -> str:
        res = client.post("/admin/base/open/login", json=_login_body())
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["data"]["token"]

    def _person(self, client: TestClient, token: str):
        return client.get("/admin/base/comm/person", headers={"Authorization": f"Bearer {token}"})

    def test_multi_device_parallel_login(self):
        """两台设备登录同账号，会话各自独立、互不踢出。"""
        a_token = self._login(self.client_a)
        b_token = self._login(self.client_b)
        # 两个 access token 都应能访问（关键：修复了"后登踢前登"）
        self.assertEqual(self._person(self.client_a, a_token).status_code, 200)
        self.assertEqual(self._person(self.client_b, b_token).status_code, 200)
        # 会话列表应有 2 条
        sessions = self.client_a.get(
            "/admin/base/session/list", headers={"Authorization": f"Bearer {a_token}"}
        ).json()["data"]
        self.assertEqual(sessions["total"], 2)

    def test_logout_only_current_device(self):
        """A 退出登录不影响 B 的 access 与 refresh。"""
        a_token = self._login(self.client_a)
        b_token = self._login(self.client_b)
        # A 登出
        self.client_a.post("/admin/base/open/logout", headers={"Authorization": f"Bearer {a_token}"})
        # A 的 access 已进黑名单 → 401
        self.assertEqual(self._person(self.client_a, a_token).status_code, 401)
        # B 的 access 仍有效
        self.assertEqual(self._person(self.client_b, b_token).status_code, 200)
        # B 的 refresh 仍可换发新 token
        self.assertEqual(self.client_b.post("/admin/base/open/refreshToken", json={}).status_code, 200)
        # A 的 refresh 应失败（会话已删除）
        self.assertEqual(self.client_a.post("/admin/base/open/refreshToken", json={}).status_code, 401)

    def test_revoke_other_device(self):
        """设备管理页踢出另一台设备的会话。"""
        a_token = self._login(self.client_a)
        b_token = self._login(self.client_b)
        # A 查看会话列表，定位 B 的会话（非当前）
        sessions = self.client_a.get(
            "/admin/base/session/list", headers={"Authorization": f"Bearer {a_token}"}
        ).json()["data"]["list"]
        self.assertEqual(len(sessions), 2)
        other = next(s for s in sessions if not s["current"])
        # A 踢出 B 的设备
        revoke = self.client_a.post(
            "/admin/base/session/revoke",
            headers={"Authorization": f"Bearer {a_token}"},
            json={"deviceId": other["deviceId"]},
        )
        self.assertEqual(revoke.status_code, 200)
        # B 的 access 应立即失效（jti 进黑名单）
        self.assertEqual(self._person(self.client_b, b_token).status_code, 401)
        # A 的 access 仍有效
        self.assertEqual(self._person(self.client_a, a_token).status_code, 200)

    def test_refresh_per_session_independent(self):
        """两台设备各自 refresh 成功，互不影响。"""
        self._login(self.client_a)
        self._login(self.client_b)
        self.assertEqual(self.client_a.post("/admin/base/open/refreshToken", json={}).status_code, 200)
        self.assertEqual(self.client_b.post("/admin/base/open/refreshToken", json={}).status_code, 200)

    def test_session_list_marks_current(self):
        """会话列表正确标记当前设备（仅 1 条 current=True）。"""
        a_token = self._login(self.client_a)
        self._login(self.client_b)
        sessions = self.client_a.get(
            "/admin/base/session/list", headers={"Authorization": f"Bearer {a_token}"}
        ).json()["data"]["list"]
        current = [s for s in sessions if s["current"]]
        self.assertEqual(len(current), 1)

    def test_clear_user_sessions_clears_all(self):
        """clear_user_sessions 清空用户全部会话（改密码踢全部设备的底层机制）。"""
        user_id = 987655
        clear_user_sessions(user_id)
        register_session(user_id, "s1", "r1", "j1")
        register_session(user_id, "s2", "r2", "j2")
        self.assertIsNotNone(get_session(user_id, "s1"))
        self.assertIsNotNone(get_session(user_id, "s2"))
        clear_user_sessions(user_id)
        self.assertIsNone(get_session(user_id, "s1"))
        self.assertIsNone(get_session(user_id, "s2"))


if __name__ == "__main__":
    unittest.main()
