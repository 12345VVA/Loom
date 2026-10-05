"""验证码图像加固渲染管线不变式测试（专项 §17：P1 色彩形变扰动 + 伪缺口烧票）。

校验逻辑与封存载荷零改动，因此既有 captcha 测试必须原样通过；本文件只覆盖
新渲染路径的构造性不变式（尺寸/咬合/间距/色调/开关回退/响应契约）。
"""

from __future__ import annotations

import base64
import io
import json
import os
import random
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.modules.base.service.auth_captcha_render import (  # noqa: E402
    PUZZLE_SHAPES,
    RenderParams,
    build_puzzle_mask,
    layout_decoys,
    render_slider_captcha,
)
from app.modules.base.service.auth_service import AuthService  # noqa: E402
from tests.helpers import captcha_target_x  # noqa: E402

_PUZZLE_SIZE = 44
_TRACK_WIDTH = 300
_TRACK_HEIGHT = 120


class ShapeLibraryTests(unittest.TestCase):
    """形状库：全形状可渲染、画布尺寸恒定、覆盖率合理（凸舌等异形不出框）。"""

    def test_shape_library_all_renderable(self):
        rng = random.Random(20261005)
        for shape in PUZZLE_SHAPES:
            for theta in (-8.0, -3.0, 3.0, 8.0):
                mask = build_puzzle_mask(shape, _PUZZLE_SIZE, theta, rng)
                self.assertEqual(mask.size, (_PUZZLE_SIZE, _PUZZLE_SIZE), shape)
                hist = mask.histogram()
                opaque = sum(hist[200:])
                transparent = sum(hist[:50])
                self.assertGreater(opaque, 0, f"{shape} 无不透明像素")
                self.assertGreater(transparent, 0, f"{shape} 无透明像素（非形状区必须透明）")
                coverage = opaque / (mask.width * mask.height)
                # 覆盖率过小=形状退化难辨认，过大≈满画布=异形失效
                self.assertTrue(0.25 <= coverage <= 0.98, f"{shape} 覆盖率异常: {coverage:.2f}")

    def test_unknown_shape_rejected(self):
        with self.assertRaises(ValueError):
            build_puzzle_mask("hexagon", _PUZZLE_SIZE, 0.0, random.Random(1))


class RenderPipelineTests(unittest.TestCase):
    """渲染管线：尺寸不变式 / 咬合不变式 / 色调通道 / 伪缺口间距。"""

    def setUp(self):
        self.rng = random.Random(20261005)

    def test_perturbed_output_dimensions_invariant(self):
        """前端零改动前提：bg 300×120、slider 44×44 RGBA、四角透明。"""
        result = render_slider_captcha(
            _TRACK_WIDTH, _TRACK_HEIGHT, 100, 30, _PUZZLE_SIZE, rng=self.rng, params=RenderParams()
        )
        self.assertEqual(result.bg.size, (_TRACK_WIDTH, _TRACK_HEIGHT))
        self.assertEqual(result.bg.mode, "RGB")
        self.assertEqual(result.slider.size, (_PUZZLE_SIZE, _PUZZLE_SIZE))
        self.assertEqual(result.slider.mode, "RGBA")
        alpha = result.slider.getchannel("A")
        for corner in ((0, 0), (_PUZZLE_SIZE - 1, 0), (0, _PUZZLE_SIZE - 1), (_PUZZLE_SIZE - 1, _PUZZLE_SIZE - 1)):
            self.assertEqual(alpha.getpixel(corner), 0, "四角必须透明（异形轮廓，PNG alpha 承载）")

    def test_bite_mask_identity(self):
        """咬合不变式：拼图块 alpha 与洞口遮罩逐字节相等（单实例遮罩构造性保证）。"""
        result = render_slider_captcha(
            _TRACK_WIDTH, _TRACK_HEIGHT, 60, 20, _PUZZLE_SIZE, rng=self.rng, params=RenderParams()
        )
        self.assertEqual(result.slider.getchannel("A").tobytes(), result.hole_mask.tobytes())

    def test_tint_channel_discriminates(self):
        """判别通道：tints 互异且数量 = 1 + 伪缺口数（tints[0]=真缺口=拼图块色调）。"""
        for seed in range(20):
            result = render_slider_captcha(
                _TRACK_WIDTH,
                _TRACK_HEIGHT,
                60 + seed,
                20,
                _PUZZLE_SIZE,
                rng=random.Random(seed),
                params=RenderParams(),
            )
            self.assertEqual(len(result.tints), 1 + len(result.decoys))
            self.assertEqual(len(set(result.tints)), len(result.tints), f"seed={seed} 色调出现碰撞")

    def test_decoy_shapes_differ_from_piece(self):
        """伪缺口异形（形状判别通道）：形状合法、互异，且数量与 decoys 一致。"""
        for seed in range(20):
            result = render_slider_captcha(
                _TRACK_WIDTH,
                _TRACK_HEIGHT,
                60 + seed,
                20,
                _PUZZLE_SIZE,
                rng=random.Random(seed),
                params=RenderParams(),
            )
            self.assertEqual(len(result.decoy_shapes), len(result.decoys))
            self.assertEqual(len(set(result.decoy_shapes)), len(result.decoy_shapes), f"seed={seed} 伪缺口形状重复")
            for shape in result.decoy_shapes:
                self.assertIn(shape, PUZZLE_SHAPES)

    def test_decoy_spacing_invariant(self):
        """烧票有效性回归：伪缺口与真缺口/彼此 Chebyshev ≥ 64，且与 target_x 距离必超容差。"""
        rng = random.Random(20261005)
        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        for _ in range(200):
            target = (rng.randint(8, _TRACK_WIDTH - _PUZZLE_SIZE - 8), rng.randint(0, _TRACK_HEIGHT - _PUZZLE_SIZE))
            count = rng.randint(1, 2)
            decoys = layout_decoys(rng, target, count, _PUZZLE_SIZE, _TRACK_WIDTH, _TRACK_HEIGHT)
            self.assertLessEqual(len(decoys), count)
            for dx, dy in decoys:
                self.assertTrue(8 <= dx <= _TRACK_WIDTH - _PUZZLE_SIZE - 8, "伪缺口必须与真缺口同横向带")
                self.assertTrue(0 <= dy <= _TRACK_HEIGHT - _PUZZLE_SIZE)
                chevy = max(abs(dx - target[0]), abs(dy - target[1]))
                self.assertGreaterEqual(chevy, _PUZZLE_SIZE + 20, "间距不变式破坏")
                self.assertGreater(abs(dx - target[0]), tolerance, "伪缺口落入容差带 → 烧票机制失效")


class DispatchToggleTests(unittest.TestCase):
    """总开关分派：False 走 legacy（不透明方块滑块），True 走加固管线（异形透明滑块）。"""

    def tearDown(self):
        settings.CAPTCHA_PUZZLE_HARDENING = True

    def test_toggle_falls_back_to_legacy_path(self):
        service = object.__new__(AuthService)
        settings.CAPTCHA_PUZZLE_HARDENING = False
        bg, slider = service._render_captcha_images(_TRACK_WIDTH, _TRACK_HEIGHT, 100, 30, _PUZZLE_SIZE)
        self.assertEqual(bg.size, (_TRACK_WIDTH, _TRACK_HEIGHT))
        self.assertEqual(slider.size, (_PUZZLE_SIZE, _PUZZLE_SIZE))
        # legacy：滑块是带描边的不透明方块，四角不透明
        self.assertGreater(slider.getpixel((0, 0))[3], 0)

        settings.CAPTCHA_PUZZLE_HARDENING = True
        bg2, slider2 = service._render_captcha_images(_TRACK_WIDTH, _TRACK_HEIGHT, 100, 30, _PUZZLE_SIZE)
        self.assertEqual(slider2.getpixel((0, 0))[3], 0)
        self.assertEqual(bg2.size, (_TRACK_WIDTH, _TRACK_HEIGHT))


class IssuanceContractTests(unittest.TestCase):
    """签发契约：响应键集合零新增、data URL 往返 alpha 保留、加固路径端到端可解。"""

    def setUp(self):
        settings.CAPTCHA_PUZZLE_HARDENING = True

    def tearDown(self):
        settings.CAPTCHA_PUZZLE_HARDENING = True

    def _issue(self) -> tuple[AuthService, str, dict]:
        service = object.__new__(AuthService)
        response = service.captcha(300, 120, "#333333", client_ip="10.7.7.7")
        data = response.data
        return service, response.captcha_id, data

    def test_response_contract_zero_new_fields(self):
        """防泄漏：伪缺口坐标绝不进响应，data 键集合恰为既有 9 键。"""
        _, _, data = self._issue()
        self.assertEqual(
            set(data.keys()),
            {"type", "bg", "slider", "sliderWidth", "sliderY", "trackWidth", "tolerance", "expireSeconds", "label"},
        )

    def test_png_alpha_survives_data_url(self):
        """前端零改动前提回归：<img> 收到的 data URL 解码后 alpha 通道完整保留。"""
        _, _, data = self._issue()
        png_bytes = base64.b64decode(data["slider"].split(",", 1)[1])
        slider = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(slider.mode, "RGBA")
        self.assertEqual(slider.size, (_PUZZLE_SIZE, _PUZZLE_SIZE))
        self.assertEqual(slider.getpixel((0, 0))[3], 0)

    def test_hardened_challenge_still_solvable(self):
        """端到端：加固路径签发 → 解封答案 → 合法轨迹提交 → 校验通过（不伤合法路径）。"""
        service, captcha_id, data = self._issue()
        self.assertEqual(data["type"], "slider")
        target_x = captcha_target_x(captcha_id)

        # 数据合法性：bg/slider 均为可解码图片
        for key in ("bg", "slider"):
            raw = base64.b64decode(data[key].split(",", 1)[1])
            self.assertIsNotNone(Image.open(io.BytesIO(raw)).size)

        steps = 6
        track = [{"x": round(target_x * step / steps, 2), "t": step * 120} for step in range(1, steps + 1)]
        verify_code = json.dumps({"x": round(target_x, 2), "duration": steps * 120, "track": track})
        service.captcha_check(captcha_id, verify_code, client_ip="10.7.7.7")  # 不抛即通过


if __name__ == "__main__":
    unittest.main()
