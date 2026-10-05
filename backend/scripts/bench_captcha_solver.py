"""滑块验证码解题基准（专项 §17：P1 图像加固验收）。

复刻报告 §13 的朴素求解器手法——**刻意不做任何加强**：
背景按 255/(255-110) 反向补偿亮度 → 拼图块内缩 3px 取模板 → RGB 三通道 MAD
滑窗 argmin（x 向扫描、y 已知，对攻击者最乐观的口径）。不感知色调、不搜索
旋转角——这正是加固要打击的对象。

- legacy profile：复现基线自证基准器有效（§13 实测 ≈36/36、偏差 0px）。
- hardened profile：加固渲染管线（auth_captcha_render）下的命中率/偏差分布/
  伪缺口误选率/渲染耗时。

手动运行（不入 CI）：pytest 只收集 tests/，本文件名亦非 test_*。
用法：python scripts/bench_captcha_solver.py --n 50 --profile both [--seed 42] [--timing] [--dump-samples DIR]
"""

from __future__ import annotations

import argparse
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
    """x 向滑窗 MAD argmin。返回 (拼图块原点 x 估计, 最优-次优 margin)。

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
    hits = zero = mispicks = 0
    buckets = {"0": 0, "1-3": 0, "4-12": 0, ">12": 0}
    margins: list[float] = []
    durations: list[float] = []
    for index, (tx, ty) in enumerate(truths):
        start = time.perf_counter()
        bg, slider, decoys = _render(profile, tx, ty, params)
        durations.append(time.perf_counter() - start)

        guess, margin = _solve(bg, slider, ty)
        deviation = abs(guess - tx)
        if deviation <= _TOLERANCE:
            hits += 1
        if deviation == 0:
            zero += 1
        key = "0" if deviation == 0 else ("1-3" if deviation <= 3 else ("4-12" if deviation <= _TOLERANCE else ">12"))
        buckets[key] += 1
        if any(dx <= guess < dx + _SIZE for dx, _ in decoys):
            mispicks += 1
        margins.append(margin)

        if dump_dir and index < 10:
            path = Path(dump_dir)
            path.mkdir(parents=True, exist_ok=True)
            bg.save(path / f"{profile}_{index:02d}_bg.png")
            slider.save(path / f"{profile}_{index:02d}_slider.png")

    return {
        "profile": profile,
        "n": n,
        "hit_rate": hits / n,
        "zero_rate": zero / n,
        "buckets": buckets,
        "decoy_mispick_rate": (mispicks / n) if decoys_possible(profile) else None,
        "margin_p50": statistics.median(margins),
        "render_p50_ms": statistics.median(durations) * 1000 if timing else None,
        "render_p95_ms": sorted(durations)[min(n - 1, int(n * 0.95))] * 1000 if timing else None,
    }


def decoys_possible(profile: str) -> bool:
    return profile != "legacy"


def _main() -> None:
    parser = argparse.ArgumentParser(description="滑块验证码解题基准（§17）")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--profile", choices=("legacy", "hardened", "both"), default="both")
    parser.add_argument("--seed", type=int, default=42)
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
        print(f"命中率(±{_TOLERANCE}) : {table['hit_rate']:.1%}")
        print(f"0px 偏差占比     : {table['zero_rate']:.1%}")
        print(f"偏差分布          : {table['buckets']}")
        if table["decoy_mispick_rate"] is not None:
            print(f"伪缺口误选占比    : {table['decoy_mispick_rate']:.1%}")
        print(f"argmin margin p50 : {table['margin_p50']:.2f}")
        if table["render_p50_ms"] is not None:
            print(f"渲染耗时 p50/p95  : {table['render_p50_ms']:.1f}ms / {table['render_p95_ms']:.1f}ms")


if __name__ == "__main__":
    _main()
