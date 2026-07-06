"""
Task 1.2 / 1.3 / 1.10 安全修复测试

覆盖：
- Task 1.2: refresh_token 服务端缓存校验 + logout 删除缓存
- Task 1.3: 限流中间件可信代理链 IP 解析
- Task 1.10: captcha 参数校验
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.framework.middleware.rate_limit import _get_client_ip  # noqa: E402
from app.modules.base.service.auth_service import _get_request_ip  # noqa: E402
from app.modules.base.service.cache_service import cache_delete_pattern  # noqa: E402
from main import app  # noqa: E402


class _MockClient:
    def __init__(self, host: str | None):
        self.host = host


class _MockRequest:
    """轻量 Request 替身，仅包含 _get_client_ip / _get_request_ip 所需属性。"""

    def __init__(self, headers: dict[str, str] | None = None, client_host: str | None = None):
        self.headers = headers or {}
        self.client = _MockClient(client_host) if client_host else None


def _slider_verify_code(captcha_data: dict) -> str:
    # 图像滑块不再返回 targetX，从服务端缓存读取答案构造合法轨迹
    from app.modules.base.service.auth_service import AuthService
    from app.modules.base.service.cache_service import cache_get

    captcha_id = captcha_data["captchaId"]
    cached = cache_get(AuthService._build_captcha_cache_key(captcha_id))
    target_x = int(json.loads(cached)["target_x"])
    track = [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)]
    return json.dumps({"x": target_x, "duration": 720, "track": track})


class CaptchaValidationTests(unittest.TestCase):
    """Task 1.10: captcha 参数校验"""

    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_captcha_rejects_width_below_min(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 79, "height": 100, "color": "#333333"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_rejects_width_above_max(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 301, "height": 100, "color": "#333333"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_rejects_height_below_min(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 150, "height": 79, "color": "#333333"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_rejects_height_above_max(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 150, "height": 301, "color": "#333333"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_rejects_invalid_color_short(self):
        # #RGB 不符合 #RRGGBB 格式
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 150, "height": 80, "color": "#333"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_rejects_invalid_color_name(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 150, "height": 80, "color": "red"},
        )
        self.assertEqual(res.status_code, 400)

    def test_captcha_accepts_valid_params(self):
        res = self.client.get(
            "/admin/base/open/captcha",
            params={"width": 200, "height": 100, "color": "#FF0000"},
        )
        self.assertEqual(res.status_code, 200)

    def test_captcha_accepts_default_params(self):
        res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(res.status_code, 200)


class RefreshTokenCacheTests(unittest.TestCase):
    """Task 1.2: refresh_token 服务端缓存校验 + logout 删除缓存"""

    def setUp(self):
        cache_delete_pattern("login:fail:*")
        cache_delete_pattern("login:lock:*")
        cache_delete_pattern("admin:token:refresh:*")
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _do_login(self) -> dict:
        captcha_res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(captcha_res.status_code, 200)
        captcha_data = captcha_res.json()["data"]
        login_res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "captchaId": captcha_data["captchaId"],
                "verifyCode": _slider_verify_code(captcha_data),
            },
        )
        self.assertEqual(login_res.status_code, 200)
        return login_res.json()["data"]

    def test_refresh_token_works_after_login(self):
        """基线：登录后 refresh_token 可正常刷新。"""
        login_data = self._do_login()
        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": login_data["refreshToken"]},
        )
        self.assertEqual(refresh_res.status_code, 200)

    def test_refresh_token_rejected_after_logout(self):
        """logout 后旧 refresh_token 刷新应 401。"""
        login_data = self._do_login()
        token = login_data["token"]
        refresh_token = login_data["refreshToken"]

        logout_res = self.client.post(
            "/admin/base/open/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_res.status_code, 200)

        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": refresh_token},
        )
        self.assertEqual(refresh_res.status_code, 401)

    def test_refresh_token_rejected_when_cache_missing(self):
        """refresh_token 缓存被清除后刷新应 401。"""
        login_data = self._do_login()
        refresh_token = login_data["refreshToken"]

        # 模拟会话被清除（管理员强制下线/踢出）：refresh 依赖会话记录，会话删除即拒
        cache_delete_pattern("admin:sess:*")

        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": refresh_token},
        )
        self.assertEqual(refresh_res.status_code, 401)

    def test_refresh_token_rejected_with_stale_value(self):
        """旧 refresh_token（已被新值覆盖）刷新应 401。"""
        login_data = self._do_login()
        old_refresh_token = login_data["refreshToken"]

        # 第一次刷新会使旧 token 失效（缓存被新值覆盖）
        first_refresh = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": old_refresh_token},
        )
        self.assertEqual(first_refresh.status_code, 200)

        # 清除 TestClient 持久化的 refresh_token cookie（第一次刷新响应设置的新值 R2），
        # 确保控制器回退到 body 中携带的旧 refresh_token（R1），
        # 而非使用 cookie 中的新值（R2）导致校验通过。
        self.client.cookies.clear()

        # 用旧 refresh_token 再次刷新应 401
        second_refresh = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": old_refresh_token},
        )
        self.assertEqual(second_refresh.status_code, 401)


class TrustedProxyIpTests(unittest.TestCase):
    """Task 1.3: 限流中间件可信代理链 IP 解析"""

    def test_get_client_ip_ignores_forwarded_for_without_trusted_proxies(self):
        """默认不信任任何代理时，X-Forwarded-For 应被忽略，使用 socket IP。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"},
            client_host="9.9.9.9",
        )
        with patch.object(settings, "TRUSTED_PROXIES", ""):
            self.assertEqual(_get_client_ip(request), "9.9.9.9")

    def test_get_client_ip_uses_forwarded_for_with_trusted_proxies(self):
        """配置可信代理后，从右向左取第一个非可信 IP 作为真实客户端。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "1.2.3.4, 10.0.0.2, 10.0.0.3"},
            client_host="10.0.0.3",
        )
        with patch.object(settings, "TRUSTED_PROXIES", "10.0.0.2,10.0.0.3"):
            self.assertEqual(_get_client_ip(request), "1.2.3.4")

    def test_get_client_ip_returns_socket_when_all_proxies_trusted(self):
        """全部 IP 都是可信代理时，回退到 socket IP。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "10.0.0.2, 10.0.0.3"},
            client_host="10.0.0.3",
        )
        with patch.object(settings, "TRUSTED_PROXIES", "10.0.0.2,10.0.0.3"):
            self.assertEqual(_get_client_ip(request), "10.0.0.3")

    def test_get_client_ip_returns_unknown_without_socket(self):
        """无 socket 连接时返回 unknown。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "1.2.3.4"},
            client_host=None,
        )
        with patch.object(settings, "TRUSTED_PROXIES", ""):
            self.assertEqual(_get_client_ip(request), "unknown")

    def test_get_request_ip_ignores_forwarded_for_without_trusted_proxies(self):
        """auth_service._get_request_ip 同步修复：默认不信任 X-Forwarded-For。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "1.2.3.4"},
            client_host="9.9.9.9",
        )
        with patch.object(settings, "TRUSTED_PROXIES", ""):
            self.assertEqual(_get_request_ip(request), "9.9.9.9")

    def test_get_request_ip_uses_forwarded_for_with_trusted_proxies(self):
        """auth_service._get_request_ip：配置可信代理后从右向左取第一个非可信 IP。"""
        request = _MockRequest(
            headers={"x-forwarded-for": "1.2.3.4, 10.0.0.2"},
            client_host="10.0.0.2",
        )
        with patch.object(settings, "TRUSTED_PROXIES", "10.0.0.2"):
            self.assertEqual(_get_request_ip(request), "1.2.3.4")

    def test_get_request_ip_returns_none_for_none_request(self):
        self.assertIsNone(_get_request_ip(None))

    def test_get_request_ip_returns_none_without_socket(self):
        request = _MockRequest(headers={}, client_host=None)
        with patch.object(settings, "TRUSTED_PROXIES", ""):
            self.assertIsNone(_get_request_ip(request))


if __name__ == "__main__":
    unittest.main()
