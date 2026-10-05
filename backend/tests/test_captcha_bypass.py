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
        cached = cache_get(AuthService._build_captcha_cache_key(captcha_id))
        self.assertIsNotNone(cached)
        return int(json.loads(cached)["target_x"])

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


if __name__ == "__main__":
    unittest.main()
