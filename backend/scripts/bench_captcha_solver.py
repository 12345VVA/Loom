"""滑块验证码解题基准（专项 §17/§18/§19：图像加固验收 + 二次修复 + 二次验收红线）。

**教训一（§18）**：第一轮基准只测了自家求解器（S1），得出「命中 12-16%≈盲猜」的错误
结论——验收方换三条路径（形状 IoU / 明度 argmax / sliderY 侧信道）即 96.7-100%。
**教训二（§19，二次验收）**：单缺口模式下 1/k 下界恒等于 100%（k=1），把「定位」
这一最难步骤的收益记作免费——必须改用**真实盲猜下界**（不放图直接猜 x，
P=(2·tol+1)/(max_x+1)≈9.7%），且必须固定包含**定位策略**。

策略清单（全部只用响应公开字段 bg/slider/sliderY/tolerance/sliderWidth）：
- S1 §13 亮度补偿 ×255/145 + 滑窗模板 MAD（内容匹配）
- S2 定位缺口后随机挑候选（多缺口判别下界）
- S3 取锚点 y 最接近 sliderY 的候选（sliderY 侧信道）
- S4 候选掩码内均值色相与拼图块均值色相距离最小（色调通道）
- S5 候选掩码内均值明度最暗
- S6 候选掩码 bbox 归一化后与拼图块 alpha 求 IoU 取最大（形状比较器）
- S7 候选掩码内均值明度最亮（明度通道）
- A1 色度连通块定位（HSV S>70 → 开运算 → 最大连通块 bbox 左上 x）——单缺口模式下定位即答案
- A2 色度滑窗定位（S 通道 44×44 滑窗均值 argmax，不用 sliderY）
- A3 亮度滑窗定位（L 通道 44×44 滑窗均值 argmin，**完全不用色调**——洞内 0.57×背景
  的 43% 灰度落差是独立于色调的定位通道）

红线（§19）：hardened 的任一定位/判别策略不显著优于真实盲猜下界 9.7% 才可宣称
「抗解」；当前单缺口模式下 A1/A2 = 100% 属**已接受的范式终态**（UX 减速带定位，
见专项报告 §18.7/§19 与设计文档 §7），基准只负责如实测量、防止宣称漂移。

- legacy profile：复现基线自证基准器有效（§13 实测 ≈36/36、偏差 0px），无伪缺口故只跑 S1。
- hardened profile：加固渲染管线（auth_captcha_render）下全策略命中率/偏差分布/
  伪缺口误选率/渲染耗时。

手动运行（不入 CI）：pytest 只收集 tests/，本文件名亦非 test_*。
用法：python scripts/bench_captcha_solver.py --n 120 --profile both [--seed 20261005] [--timing] [--dump-samples DIR]
"""

from __future__ import annotations

import argparse
import colorsys
import random
import statistics
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from PIL import Image, ImageFilter  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.base.service.auth_captcha import (  # noqa: E402
    CAPTCHA_RENDER_HEIGHT,
    CAPTCHA_RENDER_WIDTH,
)
from app.modules.base.service.auth_captcha_render import (  # noqa: E402
    RenderParams,
    render_slider_captcha,
)
from app.modules.base.service.auth_service import AuthService  # noqa: E402

_SIZE = 44
_INSET = 3  # §13 手法：模板内缩 3px 避开描边
_DARK_ALPHA = 110
_TOLERANCE = settings.CAPTCHA_SLIDER_TOLERANCE
_TRACK_WIDTH = CAPTCHA_RENDER_WIDTH
_TRACK_HEIGHT = CAPTCHA_RENDER_HEIGHT
# 真实盲猜下界（§19）：不放图、x~U[0, track−size]，命中带 = 2·tol+1（服务端只比 x）
_BLIND_FLOOR = (2 * _TOLERANCE + 1) / (_TRACK_WIDTH - _SIZE + 1)

STRATEGIES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")
STRATEGY_LABELS = {
    "S1": "S1 内容匹配(§13)",
    "S2": "S2 随机挑候选",
    "S3": "S3 y最近sliderY",
    "S4": "S4 色调匹配(hue)",
    "S5": "S5 最暗候选",
    "S6": "S6 形状IoU",
    "S7": "S7 最亮候选",
}
LOC_STRATEGIES = ("A1", "A2", "A3")
LOC_LABELS = {
    "A1": "A1 色度连通块定位",
    "A2": "A2 色度滑窗定位",
    "A3": "A3 亮度滑窗定位",
}


def _compensate(img: Image.Image) -> list[tuple[int, int, int]]:
    """§13 反向补偿：缺口 = 原图 × (1−110/255)，逆变换 = ×255/(255−110)，越界截断。"""
    factor = 255.0 / (255.0 - _DARK_ALPHA)
    return [
        (min(255, round(r * factor)), min(255, round(g * factor)), min(255, round(b * factor)))
        for (r, g, b) in img.convert("RGB").getdata()
    ]


def _template_pixels(piece: Image.Image) -> tuple[list[tuple[int, int, int, int, int]], int]:
    """拼图块内缩 3px 的模板，返回 ((x, y, r, g, b) 像素列表, 模板外接宽)。

    legacy 方块：内缩 3px 矩形；异形：alpha 腐蚀收缩后取形状内像素（坐标相对拼图块原点）。"""
    rgb = piece.convert("RGB")
    w, h = rgb.size
    alpha = piece.getchannel("A")
    data = list(rgb.getdata())
    if alpha.getextrema()[0] < 250:  # 异形：alpha 腐蚀收缩后取形状内像素
        core = alpha.filter(ImageFilter.MinFilter(2 * _INSET + 1))
        pixels = [(i % w, i // w, *data[i]) for i in range(w * h) if core.getdata()[i] > 128]
    else:  # legacy 方块：内缩 3px 矩形
        pixels = [(x, y, *data[y * w + x]) for y in range(_INSET, h - _INSET) for x in range(_INSET, w - _INSET)]
    return pixels, w - 2 * _INSET


def _solve(bg: Image.Image, piece: Image.Image, ty: int) -> tuple[int, float]:
    """S1：x 向滑窗 MAD argmin。返回 (拼图块原点 x 估计, 最优-次优 margin)。

    模板坐标相对拼图块原点（含内缩偏移），u 即拼图块原点 x——legacy 与异形统一。"""
    comp = _compensate(bg)
    bg_w, bg_h = bg.size
    tpl, _ = _template_pixels(piece)
    pw, ph = piece.size
    v = max(0, min(ty, bg_h - ph))
    u_low, u_high = 0, bg_w - pw

    scores: list[tuple[float, int]] = []
    for u in range(u_low, u_high + 1):
        total = 0
        for x, y, pr, pg, pb in tpl:
            br, bgc, bb = comp[(v + y) * bg_w + u + x]
            total += abs(pr - br) + abs(pg - bgc) + abs(pb - bb)
        scores.append((total / (len(tpl) * 3), u))
    scores.sort()
    best = scores[0]
    margin = scores[1][0] - best[0] if len(scores) > 1 else 0.0
    return best[1], margin


# ── 缺口提取基底（验收方同款手法：暗区分位阈值 → 开运算 → 连通域，纯 PIL 无 scipy）──


def _extract_holes(bg: Image.Image, min_area: int = 260) -> list[dict]:
    """返回候选缺口 [{x0, y0, w, h, pixels}]，坐标与 target_x/target_y 同系。

    §18.7 后缺口=灰底上的高饱和色块（洞内可能亮于背景），分割依据从「暗区」
    改「色度」（HSV S>70）——与真实攻击者视角一致。"""
    saturation = bg.convert("HSV").getchannel("S")
    width, height = saturation.size
    data = list(saturation.getdata())
    colored = Image.new("L", (width, height))
    colored.putdata([255 if value > 70 else 0 for value in data])
    opened = list(colored.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3)).getdata())

    holes: list[dict] = []
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
        # 洞口尺寸上界由 puzzle_size 封顶；下界放宽——capsule 形状只有 15px 高
        if 14 <= bbox_w <= 50 and 10 <= bbox_h <= 50:
            holes.append({"x0": x0, "y0": y0, "w": bbox_w, "h": bbox_h, "pixels": pixels})
    return holes


def _masked_mean_rgb(img: Image.Image, width: int, pixels: list[int]) -> tuple[float, float, float]:
    rgb = img.convert("RGB")
    data = rgb.getdata()
    total_r = total_g = total_b = 0.0
    for pixel in pixels:
        r, g, b = data[pixel]
        total_r += r
        total_g += g
        total_b += b
    count = len(pixels)
    return (total_r / count, total_g / count, total_b / count)


def _hue_value(rgb: tuple[float, float, float]) -> tuple[float, float]:
    """返回 (hue 0-360, value 0-255)。近灰色时 hue 不稳定——攻击者自己的问题。"""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return h * 360, v * 255


def _hue_distance(a: float, b: float) -> float:
    delta = abs(a - b) % 360
    return min(delta, 360 - delta)


def _normalized_mask(hole: dict, width: int) -> Image.Image:
    """候选掩码 bbox 归一化到 44×44（S6 IoU 比较器同款）。"""
    mask = Image.new("L", (hole["w"], hole["h"]), 0)
    for pixel in hole["pixels"]:
        mask.putpixel((pixel % width - hole["x0"], pixel // width - hole["y0"]), 255)
    return mask.resize((_SIZE, _SIZE), Image.NEAREST)


def _box_extreme(channel: Image.Image, puzzle_size: int, mode: str) -> tuple[int, int] | None:
    """A2/A3 定位（二次验收同款手法，纯 PIL）：BoxBlur(size//2) ≈ size×size 滑窗均值，
    取 argmax（mode="max"）或 argmin（mode="min"）像素，返回窗口左上角 (x, y)。

    不用 sliderY（y 亦由定位给出）——比「y 已知」口径更保守。"""
    half = puzzle_size // 2
    blurred = channel.filter(ImageFilter.BoxBlur(half))
    width, height = blurred.size
    data = blurred.getdata()
    best_index = 0
    best_value = data[0]
    for index, value in enumerate(data):
        if (mode == "max" and value > best_value) or (mode == "min" and value < best_value):
            best_value = value
            best_index = index
    x, y = best_index % width, best_index // width
    return (max(0, x - half), max(0, y - half))


def _localization_strategies(bg: Image.Image) -> dict[str, int | None]:
    """A1-A3：定位类攻击。单缺口模式下定位即答案（k=1），这是范式终态的既知度量。"""
    holes = _extract_holes(bg)
    a1 = max(holes, key=lambda hole: len(hole["pixels"]))["x0"] if holes else None
    saturation = bg.convert("HSV").getchannel("S")
    luminance = bg.convert("L")
    a2 = _box_extreme(saturation, _SIZE, "max")
    a3 = _box_extreme(luminance, _SIZE, "min")
    return {"A1": a1, "A2": a2[0] if a2 else None, "A3": a3[0] if a3 else None}


def _candidate_strategies(
    bg: Image.Image,
    piece: Image.Image,
    slider_y: int,
    pick_rng: random.Random,
) -> dict[str, int | None]:
    """S2-S7：基于缺口提取 + 各判别通道。无可检缺口时返回全 None。"""
    width = bg.size[0]
    holes = _extract_holes(bg)
    if not holes:
        return {key: None for key in STRATEGIES if key != "S1"}

    piece_alpha = list(piece.getchannel("A").getdata())
    piece_pixels = [y * _SIZE + x for y in range(_SIZE) for x in range(_SIZE) if piece_alpha[y * _SIZE + x] > 127]
    piece_mean = _masked_mean_rgb(piece, _SIZE, piece_pixels)
    piece_hue, _piece_value = _hue_value(piece_mean)
    piece_mask = piece.getchannel("A")

    stats = []
    for hole in holes:
        mean = _masked_mean_rgb(bg, width, hole["pixels"])
        hue, value = _hue_value(mean)
        norm = _normalized_mask(hole, width)
        norm_data = norm.getdata()
        piece_data = piece_mask.getdata()
        intersection = sum(1 for n, p in zip(norm_data, piece_data) if n > 127 and p > 127)
        union = sum(1 for n, p in zip(norm_data, piece_data) if n > 127 or p > 127)
        stats.append(
            {
                "x": hole["x0"],
                "y": hole["y0"],
                "hue": hue,
                "value": value,
                "iou": intersection / union if union else 0.0,
            }
        )

    return {
        "S2": pick_rng.choice(stats)["x"],
        "S3": min(stats, key=lambda s: abs(s["y"] - slider_y))["x"],
        "S4": min(stats, key=lambda s: _hue_distance(s["hue"], piece_hue))["x"],
        "S5": min(stats, key=lambda s: s["value"])["x"],
        "S6": max(stats, key=lambda s: s["iou"])["x"],
        "S7": max(stats, key=lambda s: s["value"])["x"],
    }


def _render(
    profile: str, tx: int, ty: int, params: RenderParams
) -> tuple[Image.Image, Image.Image, list[tuple[int, int]]]:
    """按 profile 渲染一张验证码，返回 (bg, slider, decoys)。真值 (tx, ty) 由外部给定。"""
    if profile == "legacy":
        service = object.__new__(AuthService)
        old = settings.CAPTCHA_PUZZLE_HARDENING
        settings.CAPTCHA_PUZZLE_HARDENING = False
        try:
            bg, slider = service._render_captcha_images(_TRACK_WIDTH, _TRACK_HEIGHT, tx, ty, _SIZE)
        finally:
            settings.CAPTCHA_PUZZLE_HARDENING = old
        return bg, slider, []
    result = render_slider_captcha(_TRACK_WIDTH, _TRACK_HEIGHT, tx, ty, _SIZE, params=params)
    return result.bg, result.slider, result.decoys


def _run(
    profile: str,
    truths: list[tuple[int, int]],
    params: RenderParams,
    *,
    timing: bool,
    dump_dir: str | None,
) -> dict:
    n = len(truths)
    hits = {key: 0 for key in STRATEGIES}
    attempts = {key: 0 for key in STRATEGIES}
    loc_hits = {key: 0 for key in LOC_STRATEGIES}
    zero = 0
    mispicks = 0
    buckets = {"0": 0, "1-3": 0, "4-12": 0, ">12": 0}
    margins: list[float] = []
    durations: list[float] = []
    rand_floor = 0.0
    cand_total = 0
    pick_rng = random.Random(97531)  # S2 专用（与真值 rng 隔离，不影响可复现性）
    for index, (tx, ty) in enumerate(truths):
        start = time.perf_counter()
        bg, slider, decoys = _render(profile, tx, ty, params)
        durations.append(time.perf_counter() - start)

        # S1 内容匹配（两 profile 通用自证）
        guess, margin = _solve(bg, slider, ty)
        deviation = abs(guess - tx)
        hits["S1"] += deviation <= _TOLERANCE
        attempts["S1"] += 1
        if deviation == 0:
            zero += 1
        key = "0" if deviation == 0 else ("1-3" if deviation <= 3 else ("4-12" if deviation <= _TOLERANCE else ">12"))
        buckets[key] += 1
        if any(dx <= guess < dx + _SIZE for dx, _ in decoys):
            mispicks += 1
        margins.append(margin)

        # A1-A3 定位策略（§19 红线：单缺口模式下定位即答案，必测）
        # S2-S7 判别策略仅在多缺口（k>1）下有意义——k=1 时恒中，打印只会制造噪音
        if profile != "legacy":
            for strategy, predicted in _localization_strategies(bg).items():
                if predicted is not None:
                    loc_hits[strategy] += abs(predicted - tx) <= _TOLERANCE
            candidates = _extract_holes(bg)
            cand_total += len(candidates)
            if len(candidates) > 1:
                rand_floor += 1.0 / len(candidates)
                for strategy, predicted in _candidate_strategies(bg, slider, ty, pick_rng).items():
                    if predicted is None:
                        continue
                    attempts[strategy] += 1
                    hits[strategy] += abs(predicted - tx) <= _TOLERANCE

        if dump_dir and index < 10:
            path = Path(dump_dir)
            path.mkdir(parents=True, exist_ok=True)
            bg.save(path / f"{profile}_{index:02d}_bg.png")
            slider.save(path / f"{profile}_{index:02d}_slider.png")

    return {
        "profile": profile,
        "n": n,
        "hit_rate": hits["S1"] / n,
        "zero_rate": zero / n,
        "buckets": buckets,
        "strategy_hits": {key: (hits[key] / attempts[key] if attempts[key] else None) for key in STRATEGIES},
        "loc_hits": {key: loc_hits[key] / n for key in LOC_STRATEGIES} if profile != "legacy" else None,
        "cand_per_img": (cand_total / n) if profile != "legacy" else None,
        "rand_floor": (rand_floor / n) if profile != "legacy" else None,
        "decoy_mispick_rate": (mispicks / n) if profile != "legacy" else None,
        "margin_p50": statistics.median(margins),
        "render_p50_ms": statistics.median(durations) * 1000 if timing else None,
        "render_p95_ms": sorted(durations)[min(n - 1, int(n * 0.95))] * 1000 if timing else None,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="滑块验证码解题基准（§17/§18）")
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--profile", choices=("legacy", "hardened", "both"), default="both")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--dump-samples", type=str, default=None, help="落盘前 10 张渲染样图供人工目检")
    args = parser.parse_args()

    # 生产幅度参数（settings.CAPTCHA_HARDEN_*），与签发路径一致
    service = object.__new__(AuthService)
    params = service._captcha_render_params()

    profiles = ("legacy", "hardened") if args.profile == "both" else (args.profile,)
    for profile in profiles:
        rng = random.Random(args.seed)
        truths = [
            (rng.randint(8, _TRACK_WIDTH - _SIZE - 8), rng.randint(0, _TRACK_HEIGHT - _SIZE)) for _ in range(args.n)
        ]
        table = _run(profile, truths, params, timing=args.timing, dump_dir=args.dump_samples)
        print(f"\n=== {table['profile']} (n={table['n']}) ===")
        print(f"S1 命中率(±{_TOLERANCE}) : {table['hit_rate']:.1%}")
        print(f"S1 0px 偏差占比     : {table['zero_rate']:.1%}")
        print(f"S1 偏差分布          : {table['buckets']}")
        if table["loc_hits"] is not None:
            multi = (table["cand_per_img"] or 0) > 1.0
            print(f"真实盲猜下界        : {_BLIND_FLOOR:.1%}（不放图猜 x；单缺口下 1/k 恒 100% 不可用，§19）")
            print(f"候选/图             : {table['cand_per_img']:.3f}")
            for key in LOC_STRATEGIES:
                print(f"{LOC_LABELS[key]:<18} : {table['loc_hits'][key]:.1%}")
            if multi:
                print(f"随机下界(1/k)       : {table['rand_floor']:.1%}")
                for key in ("S2", "S3", "S4", "S5", "S6", "S7"):
                    rate = table["strategy_hits"][key]
                    print(f"{STRATEGY_LABELS[key]:<18} : {rate:.1%}" if rate is not None else f"{key}: n/a")
                print(f"伪缺口误选占比      : {table['decoy_mispick_rate']:.1%}")
        print(f"argmin margin p50   : {table['margin_p50']:.2f}")
        if table["render_p50_ms"] is not None:
            print(f"渲染耗时 p50/p95    : {table['render_p50_ms']:.1f}ms / {table['render_p95_ms']:.1f}ms")


if __name__ == "__main__":
    _main()
