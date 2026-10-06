"""验证码图像加固渲染管线不变式测试（专项 §17/§18：P1 色彩形变扰动 + 伪缺口烧票 + 验收复审二次修复）。

校验逻辑与封存载荷零改动，因此既有 captcha 测试必须原样通过；本文件只覆盖
新渲染路径的构造性不变式（尺寸/咬合/间距/色调/开关回退/响应契约），以及验收
报告 S3/S6/S7 三条确定性旁路对应的输出级防回归断言（形状零信号/同行/明度解绑）。
"""

from __future__ import annotations

import base64
import colorsys
import io
import json
import os
import random
import sys
import unittest

from PIL import Image, ImageFilter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.modules.base.service.auth_captcha_render import (  # noqa: E402
    PUZZLE_SHAPES,
    RenderParams,
    build_puzzle_mask,
    layout_decoys,
    pick_tints,
    render_slider_captcha,
)
from app.modules.base.service.auth_service import AuthService  # noqa: E402
from tests.helpers import captcha_target_x  # noqa: E402

_PUZZLE_SIZE = 44
_TRACK_WIDTH = 300
_TRACK_HEIGHT = 120


def _segment_holes(bg: Image.Image, min_area: int = 260) -> list[tuple[int, int, int, int, list[int]]]:
    """输出级缺口提取（纯 PIL）：HSV 饱和度阈值 → 3×3 开运算 → BFS 连通域。

    §18.7 后缺口=灰底上的高饱和色块（洞内可能亮于背景），分割依据从「暗区」改
    「色度」——与真实攻击者视角一致。返回 [(x0, y0, bbox_w, bbox_h, 像素下标列表)]。"""
    saturation = bg.convert("HSV").getchannel("S")
    width, height = saturation.size
    data = list(saturation.getdata())
    colored = Image.new("L", (width, height))
    colored.putdata([255 if value > 70 else 0 for value in data])
    opened = list(colored.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3)).getdata())

    holes: list[tuple[int, int, int, int, list[int]]] = []
    visited = bytearray(len(opened))
    for start, value in enumerate(opened):
        if not value or visited[start]:
            continue
        visited[start] = 1
        stack = [start]
        pixels: list[int] = []
        while stack:
            pixel = stack.pop()
            pixels.append(pixel)
            px, py = pixel % width, pixel // width
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbor = ny * width + nx
                    if opened[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)
        if len(pixels) < min_area:
            continue
        xs = [p % width for p in pixels]
        ys = [p // width for p in pixels]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        bbox_w, bbox_h = x1 - x0 + 1, y1 - y0 + 1
        if 14 <= bbox_w <= 50 and 10 <= bbox_h <= 50:
            holes.append((x0, y0, bbox_w, bbox_h, pixels))
    return holes


def _normalized_hole_mask(hole: tuple[int, int, int, int, list[int]], width: int) -> Image.Image:
    """候选掩码 bbox 归一化到 44×44（S6 IoU 比较器同款）。"""
    x0, y0, bbox_w, bbox_h, pixels = hole
    mask = Image.new("L", (bbox_w, bbox_h), 0)
    for pixel in pixels:
        mask.putpixel((pixel % width - x0, pixel // width - y0), 255)
    return mask.resize((_PUZZLE_SIZE, _PUZZLE_SIZE), Image.NEAREST)


def _mask_iou(a: Image.Image, b: Image.Image) -> float:
    pa = a.getdata()
    pb = b.getdata()
    intersection = sum(1 for x, y in zip(pa, pb) if x > 127 and y > 127)
    union = sum(1 for x, y in zip(pa, pb) if x > 127 or y > 127)
    return intersection / union if union else 0.0


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

    def test_tint_brightness_not_bound_to_truth(self):
        """S7 防回归（明度解绑）：真缺口色调（tints[0]）的明度不得固定占据最亮档——
        洗牌前「掩码内均值明度 argmax」曾 99.2% 命中。同时校验调色板明度仍逐档错开
        （≥30，色觉障碍用户两两可分的无障碍性保留）。"""
        brightest = darkest = 0
        rounds = 300
        for seed in range(rounds):
            tints = pick_tints(random.Random(seed), 3)
            values = sorted(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[2] * 255 for r, g, b in tints)
            for left, right in zip(values, values[1:]):
                self.assertGreaterEqual(right - left, 30.0, f"seed={seed} 调色板明度档距不足（无障碍性受损）")
            true_value = colorsys.rgb_to_hsv(*[c / 255 for c in tints[0]])[2] * 255
            if true_value == values[-1]:
                brightest += 1
            if true_value == values[0]:
                darkest += 1
        # 洗牌后真缺口应均匀落在各明度档（≈1/3）；90% 上界防退化、远离 100% 旧泄漏
        self.assertLess(brightest, rounds * 0.9, "真缺口恒为最亮档（S7 明度通道泄漏）")
        self.assertLess(darkest, rounds * 0.9, "真缺口恒为最暗档（反向明度通道泄漏）")

    def test_brightness_channel_localizes_without_tint(self):
        """§19 P1 防回归：tint_alpha=0（完全去色调）时，纯亮度滑窗定位（A3 同款：
        BoxBlur(22)≈44×44 窗口均值 argmin）仍能找到真缺口——洞内 0.57×背景的 43%
        灰度落差是独立于色调的定位通道。「去色调提升安全性」不成立，任何未来把
        去色调当抗解手段的改动必须先推翻本断言。"""
        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        half = _PUZZLE_SIZE // 2
        hits = 0
        rounds = 20
        for seed in range(rounds):
            result = render_slider_captcha(
                _TRACK_WIDTH,
                _TRACK_HEIGHT,
                60 + seed,
                20,
                _PUZZLE_SIZE,
                rng=random.Random(seed),
                params=RenderParams(tint_alpha=0, decoy_min=0, decoy_max=0),
            )
            blurred = result.bg.convert("L").filter(ImageFilter.BoxBlur(half))
            data = list(blurred.getdata())
            best = min(range(len(data)), key=data.__getitem__)
            x = max(0, best % blurred.width - half)
            hits += abs(x - (60 + seed)) <= tolerance
        self.assertGreaterEqual(hits, rounds * 0.7, f"去色调后亮度定位命中率异常低: {hits}/{rounds}")

    def test_decoy_shapes_carry_no_signal(self):
        """S6 防回归（形状零信号）：输出级提取全部缺口，与拼图块 alpha 的归一化 IoU
        必须**两两打平**——任何「互异保证」（异形/异旋转）都会让 IoU 排序确定性指认
        真缺口（验收实测 120/120）。绝对 IoU 无意义（capsule 经 bbox 归一化拉伸后
        天然仅 ~0.38），判别只可能来自候选间差异。"""
        argmax_true = 0
        for seed in range(30):
            result = render_slider_captcha(
                _TRACK_WIDTH,
                _TRACK_HEIGHT,
                60 + seed,
                20,
                _PUZZLE_SIZE,
                rng=random.Random(seed),
                params=RenderParams(),
            )
            holes = _segment_holes(result.bg)
            self.assertGreaterEqual(len(holes), 2, f"seed={seed} 应检出 ≥2 个缺口")
            piece_mask = result.slider.getchannel("A")
            ious = [_mask_iou(_normalized_hole_mask(hole, _TRACK_WIDTH), piece_mask) for hole in holes]
            for iou in ious:
                self.assertGreaterEqual(iou, 0.30, f"seed={seed} 缺口分割疑似垃圾输出: {ious}")
            self.assertLessEqual(max(ious) - min(ious), 0.10, f"seed={seed} 候选间 IoU 差异过大（形状信号）: {ious}")
            if abs(holes[ious.index(max(ious))][0] - (60 + seed)) <= 3:
                argmax_true += 1
        self.assertLessEqual(argmax_true, 20, "IoU argmax 指认真缺口比例异常（形状通道泄漏）")

    def test_decoys_same_row_as_target(self):
        """S3 防回归（同行不变式）：输出级全部缺口锚点 y 必须相等——sliderY（=target_y）
        随响应公开且校验只比 x，伪缺口异行时「y 最接近 sliderY」即确定性指路标（96.7%）。"""
        for seed in range(30):
            result = render_slider_captcha(
                _TRACK_WIDTH,
                _TRACK_HEIGHT,
                60 + seed,
                20,
                _PUZZLE_SIZE,
                rng=random.Random(seed),
                params=RenderParams(),
            )
            holes = _segment_holes(result.bg)
            self.assertGreaterEqual(len(holes), 2, f"seed={seed} 应检出 ≥2 个缺口")
            # 分割 bbox 存在 ±1-2px 阈值噪声，同带 ≤3px 即视为同行（异行泄漏量级为数十 px）
            y0s = [hole[1] for hole in holes]
            self.assertLessEqual(max(y0s) - min(y0s), 3, f"seed={seed} 缺口不同行（y 侧信道）: {y0s}")

    def test_decoy_spacing_invariant(self):
        """烧票有效性回归：伪缺口与真缺口/彼此 |dx| ≥ 64（同行后 Chebyshev 即 |dx|），
        且与 target_x 距离必超容差。"""
        rng = random.Random(20261005)
        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        for _ in range(200):
            target = (rng.randint(8, _TRACK_WIDTH - _PUZZLE_SIZE - 8), rng.randint(0, _TRACK_HEIGHT - _PUZZLE_SIZE))
            count = rng.randint(1, 2)
            decoys = layout_decoys(rng, target, count, _PUZZLE_SIZE, _TRACK_WIDTH)
            self.assertLessEqual(len(decoys), count)
            for dx, dy in decoys:
                self.assertTrue(8 <= dx <= _TRACK_WIDTH - _PUZZLE_SIZE - 8, "伪缺口必须与真缺口同横向带")
                self.assertEqual(dy, target[1], "伪缺口必须与真缺口同行（S3）")
                self.assertGreaterEqual(abs(dx - target[0]), _PUZZLE_SIZE + 20, "间距不变式破坏")
                self.assertGreater(abs(dx - target[0]), tolerance, "伪缺口落入容差带 → 烧票机制失效")
                for ox, oy in decoys:
                    if (ox, oy) != (dx, dy):
                        self.assertGreaterEqual(abs(dx - ox), _PUZZLE_SIZE + 20, "两两间距不变式破坏")


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


class TerminalStateInvariants(unittest.TestCase):
    """§19/§20 终态不变式（P1-2，三次验收建议）：范式假设以测试固化，防静默漂移。

    若任一断言失败 = 渲染语义发生范式级变更（定位不再平凡 / 通用模板工具链防线失守）。
    正确动作是先同步专项报告口径与设计文档 §7，再改断言——而非静默放宽阈值。
    S1 刻意在测试内独立复刻（不复用 bench）：红线的测量实现必须独立于被测方的基准。"""

    ROUNDS = 15

    @staticmethod
    def _render_production(seed: int, tx: int, ty: int):
        """单缺口生产形态：拼图块不染色（piece_tint_alpha=0，与服务适配层一致）。"""
        return render_slider_captcha(
            _TRACK_WIDTH,
            _TRACK_HEIGHT,
            tx,
            ty,
            _PUZZLE_SIZE,
            rng=random.Random(9000 + seed),
            params=RenderParams(decoy_min=0, decoy_max=0, piece_tint_alpha=0),
        )

    def test_a1_localization_is_trivial(self):
        """A1 色度连通块定位 ≥95%：单缺口模式「定位即答案」是**已接受的范式终态**——
        本断言守护的不是安全性，而是口径诚实性（有人改渲染让定位变难时，必须意识到
        这同时改变了 §19 的全部论证前提）。"""
        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        hits = 0
        for seed in range(self.ROUNDS):
            tx = 8 + (seed * 37) % 240
            ty = (seed * 23) % (_TRACK_HEIGHT - _PUZZLE_SIZE + 1)
            result = self._render_production(seed, tx, ty)
            holes = _segment_holes(result.bg)
            if holes:
                largest = max(holes, key=lambda hole: len(hole[4]))
                hits += abs(largest[0] - tx) <= tolerance
        self.assertGreaterEqual(hits / self.ROUNDS, 0.95, f"A1 定位率异常：{hits}/{self.ROUNDS}（范式假设变更？）")

    def test_generic_template_solver_stays_defeated(self):
        """§13 通用模板匹配（亮度补偿+滑窗 MAD）≤1/3：反通用工具链防线未失守。"""
        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        factor = 255.0 / (255.0 - 110)
        hits = 0
        for seed in range(self.ROUNDS):
            tx = 8 + (seed * 41) % 240
            ty = (seed * 19) % (_TRACK_HEIGHT - _PUZZLE_SIZE + 1)
            result = self._render_production(seed, tx, ty)
            bg, piece = result.bg, result.slider

            # 补偿背景（§13 手法）
            comp = [
                (
                    min(255, round(r * factor)),
                    min(255, round(g * factor)),
                    min(255, round(b * factor)),
                )
                for r, g, b in bg.convert("RGB").getdata()
            ]
            # 模板：拼图块 alpha 腐蚀收缩后的形状内像素（避开轮廓）
            alpha = piece.getchannel("A")
            core = alpha.filter(ImageFilter.MinFilter(7))
            rgb = piece.convert("RGB")
            template = [
                (x, y, *rgb.getpixel((x, y)))
                for y in range(_PUZZLE_SIZE)
                for x in range(_PUZZLE_SIZE)
                if core.getpixel((x, y)) > 128
            ]
            self.assertGreater(len(template), 100, "模板过小（渲染异常）")

            best_u, best_mad = 0, None
            for u in range(_TRACK_WIDTH - _PUZZLE_SIZE + 1):
                total = 0
                for x, y, pr, pg, pb in template:
                    br, bgc, bb = comp[(ty + y) * _TRACK_WIDTH + u + x]
                    total += abs(pr - br) + abs(pg - bgc) + abs(pb - bb)
                mad = total / (len(template) * 3)
                if best_mad is None or mad < best_mad:
                    best_mad, best_u = mad, u
            hits += abs(best_u - tx) <= tolerance

        self.assertLessEqual(hits, self.ROUNDS // 3, f"通用模板求解命中率异常: {hits}/{self.ROUNDS}（防线失守？）")


if __name__ == "__main__":
    unittest.main()
