import json
import os
import sys
import unittest
from copy import deepcopy

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.modules.base.service.cache_service import cache_delete_pattern  # noqa: E402
from main import app  # noqa: E402


class AuthAlignmentTests(unittest.TestCase):
    def setUp(self):
        cache_delete_pattern("login:fail:*")
        cache_delete_pattern("login:lock:*")
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _slider_verify_code(
        self,
        captcha_data: dict,
        *,
        x_offset: int = 0,
        duration: int = 720,
        empty_track: bool = False,
        track: list[dict] | None = None,
    ) -> str:
        challenge = captcha_data["data"]
        target_x = int(challenge["targetX"]) + x_offset

        if track is None and not empty_track:
            track = [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)]
        elif track is None:
            track = []

        return json.dumps(
            {
                "x": target_x,
                "duration": duration,
                "track": track,
            }
        )

    def _captcha_challenge(self) -> dict:
        captcha_res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(captcha_res.status_code, 200)
        captcha_data = captcha_res.json()["data"]
        self.assertEqual(captcha_data["data"]["type"], "slider")
        self.assertIn("targetX", captcha_data["data"])
        self.assertIn("tolerance", captcha_data["data"])
        return captcha_data

    def _login_with_captcha(self, captcha_data: dict, verify_code: str):
        return self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "captchaId": captcha_data["captchaId"],
                "verifyCode": verify_code,
            },
        )

    def _login_headers(self) -> dict[str, str]:
        captcha_data = self._captcha_challenge()
        login_res = self._login_with_captcha(captcha_data, self._slider_verify_code(captcha_data))
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_captcha_login_and_refresh(self):
        captcha_data = self._captcha_challenge()
        verify_code = self._slider_verify_code(captcha_data)

        login_res = self._login_with_captcha(captcha_data, verify_code)
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()["data"]
        self.assertIn("token", login_data)
        # refresh_token 仅走 HttpOnly cookie，响应体不再回传（防 XSS 凭证失窃）
        # 验证登录响应设置了 refreshToken HttpOnly cookie
        set_cookie = login_res.headers.get("set-cookie", "")
        self.assertIn("refresh_token=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        # cookie path 放宽到 /，避免被前端代理前缀（/dev、/prod）阻断携带
        self.assertIn("Path=/;", set_cookie)

        person_res = self.client.get(
            "/admin/base/comm/person",
            headers={"Authorization": f"Bearer {login_data['token']}"},
        )
        self.assertEqual(person_res.status_code, 200)
        self.assertEqual(
            person_res.json()["data"]["username"],
            settings.DEFAULT_ADMIN_USERNAME,
        )

        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": login_data["refreshToken"]},
        )
        self.assertEqual(refresh_res.status_code, 200)
        self.assertIn("token", refresh_res.json()["data"])

    def test_refresh_token_via_http_only_cookie(self):
        """验证 refreshToken 通过 HttpOnly cookie 传递的主路径（Task 1.7）。

        - 登录响应通过 Set-Cookie 下发 refreshToken HttpOnly cookie
        - refresh 请求不传 body 参数，仅靠 Cookie 头携带 refreshToken
        - 应成功换发新 access token

        注意：生产环境 cookie 带 Secure 标记，仅 HTTPS 传输；
        TestClient 走 http 不会自动回发 Secure cookie，因此这里手动从
        Set-Cookie 响应头提取 cookie 值并通过 Cookie 请求头回传，
        以模拟浏览器在 HTTPS 下对 HttpOnly cookie 的自动携带行为。
        """
        captcha_data = self._captcha_challenge()
        verify_code = self._slider_verify_code(captcha_data)
        login_res = self._login_with_captcha(captcha_data, verify_code)
        self.assertEqual(login_res.status_code, 200)

        # 从 Set-Cookie 响应头提取 refresh_token cookie 值
        set_cookie = login_res.headers.get("set-cookie", "")
        self.assertIn("refresh_token=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        # 提取 cookie 值（refresh_token=xxx; Path=...; HttpOnly; ...）
        cookie_value = set_cookie.split("refresh_token=", 1)[1].split(";", 1)[0]
        self.assertTrue(cookie_value, "应能从 Set-Cookie 头解析出 refresh_token 值")

        # 不传 refreshToken body 参数，仅通过 Cookie 头携带（模拟浏览器行为）
        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={},
            headers={"Cookie": f"refresh_token={cookie_value}"},
        )
        self.assertEqual(refresh_res.status_code, 200)
        refresh_data = refresh_res.json()["data"]
        self.assertIn("token", refresh_data)
        # 刷新后应重新下发 cookie（滚动续期）
        self.assertIn("set-cookie", refresh_res.headers)
        self.assertIn("HttpOnly", refresh_res.headers["set-cookie"])

        # 新 token 可正常访问受保护接口
        person_res = self.client.get(
            "/admin/base/comm/person",
            headers={"Authorization": f"Bearer {refresh_data['token']}"},
        )
        self.assertEqual(person_res.status_code, 200)

    def test_refresh_token_rejected_without_cookie_or_body(self):
        """验证无 cookie 且无 body 时 refresh 应返回 401。"""
        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={},
        )
        self.assertEqual(refresh_res.status_code, 401)

    def test_refresh_token_via_body_when_no_cookie(self):
        """无 cookie 时通过 body 传 refreshToken 仍可刷新（兼容路径覆盖）。

        test_captcha_login_and_refresh 的 refresh 请求会被 TestClient 自动带上
        login 的 cookie，无法证明 body 兼容分支生效；此处显式清空 cookie，
        确保仅靠 body 的 ``refreshToken`` 字段完成刷新。
        """
        captcha_data = self._captcha_challenge()
        verify_code = self._slider_verify_code(captcha_data)
        login_res = self._login_with_captcha(captcha_data, verify_code)
        self.assertEqual(login_res.status_code, 200)
        refresh_value = login_res.headers.get("set-cookie", "").split("refresh_token=", 1)[1].split(";", 1)[0]
        self.assertTrue(refresh_value)

        # 清除 TestClient 自动保存的 cookie，确保仅靠 body 传 refreshToken
        self.client.cookies.clear()
        refresh_res = self.client.post(
            "/admin/base/open/refreshToken",
            json={"refreshToken": refresh_value},
        )
        self.assertEqual(refresh_res.status_code, 200)
        self.assertIn("token", refresh_res.json()["data"])

    def test_slider_captcha_is_single_use(self):
        captcha_data = self._captcha_challenge()
        verify_code = self._slider_verify_code(captcha_data)

        first_res = self._login_with_captcha(captcha_data, verify_code)
        self.assertEqual(first_res.status_code, 200)

        second_res = self._login_with_captcha(captcha_data, verify_code)
        self.assertEqual(second_res.status_code, 401)

    def test_slider_captcha_rejects_invalid_track(self):
        wrong_position = self._captcha_challenge()
        tolerance = int(wrong_position["data"]["tolerance"])
        wrong_position_res = self._login_with_captcha(
            wrong_position,
            self._slider_verify_code(wrong_position, x_offset=tolerance + 20),
        )
        self.assertEqual(wrong_position_res.status_code, 401)

        too_fast = self._captcha_challenge()
        too_fast_res = self._login_with_captcha(
            too_fast,
            self._slider_verify_code(too_fast, duration=100),
        )
        self.assertEqual(too_fast_res.status_code, 401)

        empty_track = self._captcha_challenge()
        empty_track_res = self._login_with_captcha(
            empty_track,
            self._slider_verify_code(empty_track, empty_track=True),
        )
        self.assertEqual(empty_track_res.status_code, 401)

    def test_slider_captcha_allows_small_pointer_jitter(self):
        captcha_data = self._captcha_challenge()
        target_x = int(captcha_data["data"]["targetX"])
        jitter_track = [
            {"x": target_x * 0.18, "t": 120},
            {"x": target_x * 0.34, "t": 240},
            {"x": target_x * 0.34 - 2, "t": 300},
            {"x": target_x * 0.58, "t": 420},
            {"x": target_x * 0.78, "t": 560},
            {"x": target_x, "t": 720},
        ]

        login_res = self._login_with_captcha(
            captcha_data,
            self._slider_verify_code(captcha_data, track=jitter_track),
        )
        self.assertEqual(login_res.status_code, 200)

    def test_slider_captcha_rejects_large_backtrack(self):
        captcha_data = self._captcha_challenge()
        target_x = int(captcha_data["data"]["targetX"])
        backtrack_track = [
            {"x": target_x * 0.2, "t": 120},
            {"x": target_x * 0.65, "t": 240},
            {"x": target_x * 0.65 - settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX - 4, "t": 360},
            {"x": target_x * 0.75, "t": 480},
            {"x": target_x * 0.9, "t": 600},
            {"x": target_x, "t": 720},
        ]

        login_res = self._login_with_captcha(
            captcha_data,
            self._slider_verify_code(captcha_data, track=backtrack_track),
        )
        self.assertEqual(login_res.status_code, 401)

    def test_eps_shape_when_enabled(self):
        response = self.client.get("/admin/base/open/eps")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("base", data)
        self.assertIn("dict", data)
        self.assertTrue(any(item["prefix"] == "/admin/base/sys/user" for item in data["base"]))

    def test_permmenu_contains_flat_system_management_routes(self):
        permmenu_res = self.client.get(
            "/admin/base/comm/permmenu",
            headers=self._login_headers(),
        )
        self.assertEqual(permmenu_res.status_code, 200)
        menus = permmenu_res.json()["data"]["menus"]

        system_menu = next(item for item in menus if item["router"] == "/base/sys/user")
        role_menu = next(item for item in menus if item["router"] == "/base/sys/role")
        menu_menu = next(item for item in menus if item["router"] == "/base/sys/menu")
        param_menu = next(item for item in menus if item["router"] == "/base/sys/param")
        log_menu = next(item for item in menus if item["router"] == "/base/sys/log")
        login_log_menu = next(item for item in menus if item["router"] == "/base/sys/login_log")

        self.assertEqual(system_menu["parentId"], next(item["id"] for item in menus if item["name"] == "系统管理"))
        self.assertEqual(system_menu["viewPath"], "modules/base/views/user/index.vue")
        self.assertEqual(role_menu["viewPath"], "modules/base/views/role.vue")
        self.assertEqual(menu_menu["viewPath"], "modules/base/views/menu/index.vue")
        self.assertEqual(param_menu["viewPath"], "modules/base/views/param.vue")
        self.assertEqual(log_menu["viewPath"], "modules/base/views/log.vue")
        self.assertEqual(login_log_menu["viewPath"], "modules/base/views/login_log.vue")

    def test_person_update_and_menu_parse(self):
        headers = self._login_headers()

        update_res = self.client.post(
            "/admin/base/comm/personUpdate",
            headers=headers,
            json={"nickName": "系统管理员-测试", "remark": "updated by test"},
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertTrue(update_res.json()["data"]["success"])

        person_res = self.client.get("/admin/base/comm/person", headers=headers)
        self.assertEqual(person_res.status_code, 200)
        self.assertEqual(person_res.json()["data"]["nickName"], "系统管理员-测试")

        parse_res = self.client.post(
            "/admin/base/sys/menu/parse",
            headers=headers,
            json={"prefixes": ["/admin/base/sys/user", "/admin/task/info"]},
        )
        self.assertEqual(parse_res.status_code, 200)
        parsed = parse_res.json()["data"]["list"]
        self.assertTrue(any(item["router"] == "/base/sys/user" for item in parsed))
        self.assertTrue(any(item["router"] == "/task/list" for item in parsed))

    def test_department_list_and_menu_export_import(self):
        headers = self._login_headers()

        dept_res = self.client.get("/admin/base/sys/department/list", headers=headers)
        self.assertEqual(dept_res.status_code, 200)
        departments = dept_res.json()["data"]
        self.assertTrue(any(item["name"] == "平台" for item in departments))

        permmenu_res = self.client.get("/admin/base/comm/permmenu", headers=headers)
        system_group = next(item for item in permmenu_res.json()["data"]["menus"] if item["name"] == "系统管理")
        export_res = self.client.post(
            "/admin/base/sys/menu/export", headers=headers, json={"ids": [system_group["id"]]}
        )
        self.assertEqual(export_res.status_code, 200)
        menus = export_res.json()["data"]
        self.assertTrue(any(item["name"] == "系统管理" for item in menus))

        import_payload = {"menus": deepcopy(menus)}
        import_res = self.client.post("/admin/base/sys/menu/import", headers=headers, json=import_payload)
        self.assertEqual(import_res.status_code, 200)
        self.assertTrue(import_res.json()["data"]["success"])

    def test_sys_log_param_login_log_and_dict_endpoints(self):
        headers = self._login_headers()

        keep_res = self.client.get("/admin/base/sys/log/getKeep", headers=headers)
        self.assertEqual(keep_res.status_code, 200)
        self.assertIn(keep_res.json()["data"], ("7", "15"))

        set_keep_res = self.client.post("/admin/base/sys/log/setKeep", headers=headers, json={"value": 15})
        self.assertEqual(set_keep_res.status_code, 200)

        log_page_res = self.client.get("/admin/base/sys/log/page", headers=headers)
        self.assertEqual(log_page_res.status_code, 200)
        self.assertIn("list", log_page_res.json()["data"])

        param_add_res = self.client.post(
            "/admin/base/sys/param/add",
            headers=headers,
            json={"name": "站点公告", "keyName": "siteNotice", "data": "<p>hello</p>", "dataType": 1, "remark": "test"},
        )
        self.assertIn(param_add_res.status_code, (200, 409))

        param_html_res = self.client.get("/admin/base/sys/param/html", headers=headers, params={"key": "siteNotice"})
        self.assertEqual(param_html_res.status_code, 200)

        login_log_res = self.client.get("/admin/base/sys/login_log/page", headers=headers)
        self.assertEqual(login_log_res.status_code, 200)
        self.assertTrue(login_log_res.json()["data"]["pagination"]["total"] >= 1)

        dict_type_add = self.client.post(
            "/admin/dict/type/add",
            headers=headers,
            json={"name": "测试字典", "key": "test_dict"},
        )
        self.assertIn(dict_type_add.status_code, (200, 409))

        type_page = self.client.get("/admin/dict/type/page", headers=headers)
        self.assertEqual(type_page.status_code, 200)
        type_items = type_page.json()["data"]["list"]
        target = next(item for item in type_items if item["key"] == "test_dict")

        dict_info_add = self.client.post(
            "/admin/dict/info/add",
            headers=headers,
            json={"typeId": target["id"], "name": "测试项", "value": "1", "orderNum": 1},
        )
        self.assertIn(dict_info_add.status_code, (200, 409))

        dict_types_res = self.client.get("/admin/dict/info/types")
        self.assertEqual(dict_types_res.status_code, 200)

        dict_data_res = self.client.post("/admin/dict/info/data", headers=headers, json={"types": ["test_dict"]})
        self.assertEqual(dict_data_res.status_code, 200)
        self.assertIn("test_dict", dict_data_res.json()["data"])


if __name__ == "__main__":
    unittest.main()
