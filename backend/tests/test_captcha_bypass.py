"""验证码绕过专项回归（登录链路验证码专项分析 2026-10-05 的 C1/C2 修复验证）。

- C1：NaN/Infinity 注入使位置与轨迹比较恒 False → parse_constant 拒绝 + isfinite 纵深
- C1 边界：1e999 等数字字面量绕过 parse_constant 解析为 inf（int(inf) 曾 OverflowError 500）
- C2：客户端 width 曾直接决定答案解空间（width=80 仅 21 个候选位存在万能 x）→ 服务端固定尺寸
- L1：challenge 非法形态统一 401 而非 AttributeError 500
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.modules.base.service.auth_service import AuthService  # noqa: E402
from app.modules.base.service.cache_service import cache_delete_pattern, cache_get, cache_set  # noqa: E402
from main import app  # noqa: E402

_CAPTCHA_KEY_PREFIX = "verify:slider:"


class CaptchaBypassTests(unittest.TestCase):
    """C1/C2/L1 回归：无需图像识别的 100% 绕过路径必须被阻断。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        cache_delete_pattern(f"{_CAPTCHA_KEY_PREFIX}*")

    def tearDown(self):
        cache_delete_pattern(f"{_CAPTCHA_KEY_PREFIX}*")

    def _issue(self, **params) -> dict:
        res = self.client.get("/admin/base/open/captcha", params=params or None)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()["data"]  # CaptchaResponse: {captchaId, data: {bg, slider, trackWidth, ...}}
        return {"captchaId": body["captchaId"], "data": body["data"]}

    def _target_x(self, captcha_id: str) -> int:
        from helpers import captcha_target_x

        return captcha_target_x(captcha_id)

    def _track(self, *xs, duration: int = 720) -> str:
        points = [{"x": x, "t": (i + 1) * 120} for i, x in enumerate(xs)]
        if len(points) < settings.CAPTCHA_SLIDER_MIN_TRACK_POINTS:
            last = xs[-1] if xs else 0
            points = points + [
                {"x": last, "t": (len(points) + i + 1) * 120}
                for i in range(settings.CAPTCHA_SLIDER_MIN_TRACK_POINTS - len(points))
            ]
        return json.dumps({"x": xs[-1] if xs else 0, "duration": duration, "track": points})

    def _check(self, captcha_id: str, verify_code: str) -> None:
        # captcha_check 不依赖 session：object.__new__ 绕过 __init__ 拿一个无 session 实例
        instance = object.__new__(AuthService)
        instance.captcha_check(captcha_id, verify_code)

    # --------------------------------- C1 ---------------------------------

    def test_c1_nan_x_rejected(self):
        """NaN 注入曾使 `abs(NaN - target_x) > tolerance` 恒 False（任意配置 100% 绕过），必须 401。"""
        issue = self._issue()
        verify_code = json.dumps({"x": "NAN", "duration": 720, "track": [{"x": 1, "t": 120}]}).replace('"NAN"', "NaN")
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_c1_infinity_in_track_rejected(self):
        verify_code = json.dumps(
            {"x": 100, "duration": 720, "track": [{"x": 1, "t": 120}, {"x": "INF", "t": 240}]}
        ).replace('"INF"', "Infinity")
        issue = self._issue()
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_c1_overflow_literal_duration_rejected_not_500(self):
        """1e999 绕过 parse_constant 解析为 inf：int(inf) 抛 OverflowError，必须 401 而非 500。"""
        issue = self._issue()
        verify_code = json.dumps({"x": 100, "duration": 1e999, "track": [{"x": 1, "t": 120}]})
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_c1_valid_solve_still_passes(self):
        """对照组：合法求解路径不被新增校验误伤。"""
        issue = self._issue()
        target_x = self._target_x(issue["captchaId"])
        track = [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)]
        verify_code = json.dumps({"x": target_x, "duration": 720, "track": track})
        # 不抛异常即通过
        self._check(issue["captchaId"], verify_code)

    # --------------------------------- C2 ---------------------------------

    def test_c2_render_dimensions_server_fixed(self):
        """客户端 width 不再决定解空间：任意外参都渲染服务端固定尺寸（前端本就上报 300×120）。"""
        for width in (80, 150, 200, 300):
            issue = self._issue(width=width, height=120)
            self.assertEqual(issue["data"]["trackWidth"], 300)

    def test_c2_universal_x_at_small_width_no_longer_guaranteed(self):
        """万能 x=18（width=80 时代的恒中答案）在固定 300 宽下不再恒中：
        连续 10 次签发全部以 x=18 提交，必须出现拒绝（全中概率 ≤ (25/241)^10 ≈ 1e-10，无随机 flake）。"""
        rejected = 0
        for _ in range(10):
            issue = self._issue(width=80)
            try:
                self._check(issue["captchaId"], self._track(18))
            except HTTPException:
                rejected += 1
        self.assertGreater(rejected, 0, "x=18 连续 10 次全部通过——解空间不变式被破坏")

    def test_c2_invariant_guard_rejects_misconfigured_tolerance(self):
        """解空间不变式：容差配置过大（候选位置数 < 10×容差带）时拒绝签发而非退化。"""
        with patch.object(settings, "CAPTCHA_SLIDER_TOLERANCE", 200):
            res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(res.status_code, 500)
        self.assertIn("解空间", res.text)

    # --------------------------------- L1 ---------------------------------

    def test_l1_non_dict_challenge_401_not_500(self):
        """缓存值非 dict（健壮性场景，远程不可直接触发）时统一 401 而非 AttributeError 500。"""
        captcha_id = "0" * 32
        cache_set(AuthService._build_captcha_cache_key(captcha_id), json.dumps("garbage"), 60)
        with self.assertRaises(HTTPException) as cm:
            self._check(captcha_id, self._track(100))
        self.assertEqual(cm.exception.status_code, 401)

    # --------------------------------- H1 ---------------------------------

    def _verify(self, *, x: float, duration: int, points: list[dict]) -> str:
        return json.dumps({"x": x, "duration": duration, "track": points})

    def test_h1_track_time_going_backwards_rejected(self):
        """t 必须单调非递减（前端与 duration 同源），时间倒流属伪造载荷。"""
        issue = self._issue()
        verify_code = self._verify(
            x=100,
            duration=720,
            points=[{"x": 10, "t": 300}, {"x": 50, "t": 200}, {"x": 100, "t": 720}],
        )
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_h1_last_t_exceeds_duration_rejected(self):
        """末点时刻不得超过自报拖拽时长（同源时钟 +200ms 事件循环余量）。"""
        issue = self._issue()
        verify_code = self._verify(
            x=100,
            duration=720,
            points=[{"x": i * 20, "t": t} for i, t in enumerate((100, 200, 300, 400, 500, 2000))],
        )
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_h1_release_gap_too_large_rejected(self):
        """拖拽时长与末点时刻间隔超限（轨迹与 duration 各自编造）→ 401。"""
        issue = self._issue()
        verify_code = self._verify(
            x=100,
            duration=10000,  # ≤ TTL 窗口、≥ 最小时长，但与末点 t=720 间隔 9s > 5s
            points=[{"x": i * 20, "t": t} for i, t in enumerate((100, 200, 300, 400, 500, 720))],
        )
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_h1_duration_over_expire_window_rejected(self):
        """自报拖拽时长超过验证码时效窗口（TTL 120s）→ 伪造载荷。"""
        issue = self._issue()
        verify_code = self._verify(
            x=100,
            duration=200000,
            points=[{"x": i * 20, "t": t} for i, t in enumerate((1, 2, 3, 4, 5, 6))],
        )
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)

    def test_m2_track_point_cap_rejected(self):
        """轨迹点数超上限（M2：防超大载荷占用工作线程）→ 401。"""
        issue = self._issue()
        points = [{"x": i % 200, "t": i} for i in range(settings.CAPTCHA_SLIDER_MAX_TRACK_POINTS + 1)]
        verify_code = self._verify(x=100, duration=5000, points=points)
        with self.assertRaises(HTTPException) as cm:
            self._check(issue["captchaId"], verify_code)
        self.assertEqual(cm.exception.status_code, 401)


class CaptchaLockoutTests(unittest.TestCase):
    """H2 回归：验证码失败不得计入账号失败计数（否则仅凭用户名 5 次请求即可锁死任意账号）。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        from app.modules.base.service.cache_service import cache_delete_pattern as dp

        dp("login:fail:*")
        dp("login:lock:*")
        self.client.cookies.clear()

    def tearDown(self):
        from app.modules.base.service.cache_service import cache_delete_pattern as dp

        dp("login:fail:*")
        dp("login:lock:*")

    def _valid_captcha_login(self) -> object:
        """正确密码 + 真实求解的验证码 → 应当登录成功（200）。"""
        captcha_res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(captcha_res.status_code, 200)
        captcha_data = captcha_res.json()["data"]
        return self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "captchaId": captcha_data["captchaId"],
                "verifyCode": _valid_verify_code(captcha_data),
            },
        )

    def test_captcha_failures_do_not_lock_account(self):
        """5 次错误验证码（无凭证）后，正确凭证 + 合法验证码仍可登录——账号未被锁定。"""
        # 修复前：验证码失败计入账号计数，5 次即触发 900s 账号锁 → 下一步 429
        for _ in range(settings.BASE_LOGIN_ACCOUNT_FAIL_MAX):
            res = self.client.post(
                "/admin/base/open/login",
                json={
                    "username": settings.DEFAULT_ADMIN_USERNAME,
                    "password": settings.DEFAULT_ADMIN_PASSWORD,
                    "captchaId": None,
                    "verifyCode": None,
                },
            )
            self.assertIn(res.status_code, (401, 422), res.text)

        login_res = self._valid_captcha_login()
        self.assertEqual(
            login_res.status_code, 200, f"验证码失败不应锁账号，实际: {login_res.status_code} {login_res.text}"
        )


def _valid_verify_code(captcha_data: dict) -> str:
    """从服务端缓存读答案构造合法求解轨迹（与 test_auth_security_fixes 同法）。"""
    from helpers import captcha_target_x

    target_x = captcha_target_x(captcha_data["captchaId"])
    track = [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)]
    return json.dumps({"x": target_x, "duration": 720, "track": track})


class CaptchaHardeningTests(unittest.TestCase):
    """P2 加固：M3 答案封存 / M4 fail-closed / M1 签发限流 / L3 IP 绑定与 y 随机 / M2 入参上限。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        cache_delete_pattern("verify:slider:*")
        cache_delete_pattern("captcha:issue:*")

    def tearDown(self):
        cache_delete_pattern("verify:slider:*")
        cache_delete_pattern("captcha:issue:*")

    def test_m3_challenge_sealed_in_cache(self):
        """答案封存：Redis/缓存侧不再有明文 target_x（遍历 verify:slider:* 无法直接得分）。"""
        res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(res.status_code, 200)
        captcha_id = res.json()["data"]["captchaId"]
        cached = cache_get(f"verify:slider:{captcha_id}")
        self.assertIsNotNone(cached)
        self.assertNotIn("target_x", cached)
        # 且不是可解析的 JSON（Fernet 密文）
        with self.assertRaises(json.JSONDecodeError):
            json.loads(cached)

    def test_m4_fail_closed_when_redis_unavailable_in_production(self):
        """M4：生产（DEBUG=False）且 Redis 不可用 → 签发明确 503，而非静默降级内存
        （多进程内存互不共享，静默降级会产生「永远错」的 captchaId）。"""
        with patch.object(settings, "DEBUG", False):
            res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(res.status_code, 503)

    def test_m4_memory_fallback_allowed_in_debug(self):
        """开发环境（DEBUG=True）Redis 不可用时保持内存回退（现有开发体验不变）。"""
        self.assertTrue(settings.DEBUG)
        res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(res.status_code, 200)

    def test_m1_issue_rate_cap(self):
        """M1：签发限流——窗口内超过 CAPTCHA_ISSUE_MAX_PER_WINDOW 次 → 429。"""
        with patch.object(settings, "CAPTCHA_ISSUE_MAX_PER_WINDOW", 3):
            codes = [self.client.get("/admin/base/open/captcha").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3], 429)
        self.assertEqual(codes[4], 429)

    def test_l3_bind_ip_mismatch_rejected(self):
        """L3：验证码与签发 IP 绑定——他 IP 提交（如凭证被盗用/跨代答）→ 401；同 IP 正常通过。
        GETDEL 一次性消费：每个验证码只能校验一次；service 层直调避免依赖 IP 提取链路。"""
        from helpers import captcha_target_x

        instance = object.__new__(AuthService)

        def _issue(client_ip: str) -> str:
            resp = instance.captcha(300, 120, "#333333", client_ip=client_ip)
            return resp.captcha_id

        def _solve(captcha_id: str) -> str:
            target_x = captcha_target_x(captcha_id)
            track = [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)]
            return json.dumps({"x": target_x, "duration": 720, "track": track})

        # 签发 IP=A，提交 IP=B → 401（该验证码同时被消费）
        captcha_id = _issue("203.0.113.10")
        with self.assertRaises(HTTPException) as cm:
            instance.captcha_check(captcha_id, _solve(captcha_id), client_ip="198.51.100.77")
        self.assertEqual(cm.exception.status_code, 401)

        # 再签发一个：同 IP 提交 → 通过
        captcha_id2 = _issue("203.0.113.10")
        instance.captcha_check(captcha_id2, _solve(captcha_id2), client_ip="203.0.113.10")

    def test_l3_target_y_randomized(self):
        """L3：缺口纵向位置随机化（原恒为居中 38）。"""
        ys = set()
        for _ in range(5):
            res = self.client.get("/admin/base/open/captcha")
            ys.add(res.json()["data"]["data"]["sliderY"])
        self.assertGreater(len(ys), 1, "连续 5 次签发 sliderY 完全一致——随机化未生效")
        for y in ys:
            self.assertTrue(0 <= y <= 120 - 44)

    def test_m2_verify_code_length_cap(self):
        """M2：verify_code 超 4096 字节 → 422（DTO 层拦截，不到达业务逻辑）。"""
        res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": "x",
                "password": "x",
                "captchaId": "0" * 32,
                "verifyCode": "a" * 5000,
            },
        )
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
