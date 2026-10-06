"""滑块验证码图像加固渲染管线（专项 §13.4 P1 / §17）。

针对「拼图块=原图同区域裁剪 + 固定 alpha 叠加」这一确定性变换可被
亮度反向补偿+滑窗匹配 100% 解出的问题（§13 实测 36/36 偏差 0px），本模块实现：

- A 色彩+形变扰动：拼图块相对背景做独立亮度/对比度/色相偏移 + 内容旋转/缩放抖动，
  破坏内容相关性（色相偏移是逐像素、随色度方向变化的变换，无法用单通道全局标量补偿还原；
  旋转则迫使攻击者增加 (θ, s) 搜索维度）。
- B 异形缺口+伪缺口烧票：形状随机库 + 与真缺口同形状的伪缺口（形状零线索），
  靠色调判别通道区分（拼图块色调=真缺口色调）；选错伪缺口必然超出容差
  （间距不变式 >容差 5 倍），经 GETDEL 一次性消费烧票。

2026-10-05 验收复审后的二次修复（验收报告 S3/S6/S7，详见专项 §18）——三条不变式：
- **形状不携带真假信息**：真缺口/伪缺口/拼图块共用同一张 hole_mask（同形状同旋转）。
  初版曾让伪缺口强制异形并注释「形状即真人判别通道」，被验收方以 bbox 归一化 IoU
  比较器 100% 击穿（S6）——形状比较器是几行代码的事，任何「互异保证」都是确定性泄漏。
- **明度不与真假绑定**：判别色调调色板生成后随机洗牌，真缺口不固定取最亮档（S7
  曾以「掩码内均值明度 argmax」99.2% 命中）。色觉障碍无障碍性不受损：调色板明度
  仍逐档错开（两两可分），且拼图块与真缺口色调恒相同——匹配依据是「色调相等」，
  从来不是「明度排序」。
- **伪缺口与真缺口同行**：sliderY（=target_y）随响应公开、校验只比 x，伪缺口若异行，
  「锚点 y 最接近 sliderY」即成确定性指路标（S3 浏览器实测 96.7% 命中）。

2026-10-06 用户浏览器实测反馈（§18.7）——可用性回归与终局设计：
- **初版判别通道视觉上不成立**：alpha 52 + 洞内调制下限 0.25× 令有效色度低至
  ~13/255，人眼无法完成「拼图块↔缺口」跨亮度基线的色调匹配（教训：可用性必须
  真人浏览器验证；「缺口彼此可分」≠「任务可解」）。
- **色调拉满暴露第二个死结**：拼图块一旦高饱和染色（判别人眼所需），其平坦色调与
  洞内平坦色调在 RGB 空间直接相似——§13 求解器不读内容、纯模板匹配即 100% 复活
  （实测）。「拼图块染色浓度」是单一旋钮：S1 防御要它低、人类判别要它高，不可兼得。
- **终局：默认单缺口模式**（DECOY=0）：判别问题消失 → 拼图块不染色（piece_tint
  =0）→ 可用性满分。**安全口径（§19 二次验收校准）**：S1=0% 仅意味着击败 §13 类
  通用模板匹配工具链；单缺口模式下**定位即答案**，色度/亮度定位器（A1/A2）100%——
  验证码不提供抗自动化能力，此为滑块范式的既知终态（「定位不是安全边界」的论断
  仅在多缺口判别模式下成立，不可迁移到本模式）。判别模式（DECOY>0）保留全部
  机制（同形状/同行/洗牌/烧票）+ 高饱和色调，但明示接受 S1≈S4≈100% 的既知代价。
- **描边全部移除**（缺口外环/拼图块内环，用户要求）：描边只增加视觉噪音，
  可定位性在有无描边下均非难点。
- **背景必须真灰**（三通道同值）：通道独立随机会让背景自带色度（S 可达 96），
  污染唯一色调通道的信噪比。
- 安全定位（§19 正式采纳）：UX 减速带 + 反通用求解器工具链；抗自动化防线=
  失败锁定/限流/一次性票据——「人类判别线索必然机器可读」，滑块范式内不存在
  既可用又抗解的判别通道。

模块约束：
- 纯函数：不 import FastAPI、不读 settings、不碰 Redis——基准脚本
  （scripts/bench_captcha_solver.py）可脱离应用直接复用同一路径，保证
  「基准测的就是线上渲染的」。
- 前端零改动是硬约束：拼图块画布恒 size×size（pic-captcha.vue 以 <img> 直出 PNG、
  CSS 硬编码高 44px），非形状区域依赖 PNG alpha 透明。
- 咬合由「单实例遮罩」构造性保证：拼图块 alpha、真缺口、伪缺口共用同一张旋转后
  遮罩，±容差（12px）只需吸收人手停位误差。
"""

from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageStat

# 形状库注册表键（hexagon 剔除：44px + 2px 描边 + 暗块叠加下与 circle 几乎不可分，
# 真人误选成本（烧票）不能反噬真人）
PUZZLE_SHAPES: tuple[str, ...] = ("rounded", "knob", "circle", "capsule")
# 伪缺口最小间距 = puzzle_size + 该常量（模块常量，故意不设配置项——允许配置即允许被
# 误配成「伪缺口落在容差带内」导致烧票机制失效，沿用 C2 的「不可配坏」哲学）
_DECOY_MIN_GAP_EXTRA: int = 20
# 遮罩超采样倍数（ImageDraw 无原生抗锯齿，先放大绘制再 LANCZOS 缩回）
_SUPERSAMPLE: int = 4
# 拼图块源裁剪余量（size+2×5=54 源，覆盖 8° 旋转 + 5% 缩放的最坏内接需求）
_ROTATE_PAD: int = 10
# 缺口暗块样式（与 legacy 渲染保持一致：暗块 alpha 同为 110，不给 alpha 差异线索）
_HOLE_DARK_ALPHA: int = 110
# §13 求解器的亮度还原 LUT：x → min(255, x×255/(255−110))。拼图块以该寄存器呈现，
# 使模板亮度对齐补偿后的场域而非补偿后的暗洞（render_slider_captcha 内注释详述）
_COMPENSATE_LUT = [min(255, round(i * 255.0 / (255.0 - _HOLE_DARK_ALPHA))) for i in range(256)]


@dataclass(frozen=True)
class RenderParams:
    """加固幅度参数（由 settings.CAPTCHA_HARDEN_* 适配，便于基准脚本独立调档）。"""

    rotate_deg: float = 6.0  # 内容旋转幅度上限（°），实际 ±uniform(3, rotate_deg)
    scale: float = 0.05  # 内容缩放抖动 ±5%（只缩内容不缩轮廓，咬合不受影响）
    brightness: float = 0.20  # 拼图块亮度乘性扰动 ±20%
    contrast: float = 0.15  # 对比度 ±15%
    hue_shift: int = 30  # HSV 色相偏移幅度（0-255 刻度，30 ≈ 42°）
    tint_alpha: int = 150  # 判别色调叠加不透明度（0-255）——§18.7：52 时人眼不可辨，判别通道等于不存在
    piece_tint_alpha: int | None = None  # 拼图块染色不透明度；None=跟随 tint_alpha（判别模式），0=不染（单缺口模式）
    noise_sigma: int = 0  # 拼图块独立高斯噪声 σ（0=关；基准实测对 argmin 无效，默认关）
    hole_noise_sigma: int = 25  # 洞内内容替换噪声 σ：洞内不再保留原图内容（**结构性切断**
    # 内容匹配——「亮度反向补偿+滑窗 MAD」依赖洞内=原图×常数的确定性关系，内容被
    # 独立噪声替换后该信号不复存在）。真人判别走轮廓咬合+色调（§13.3），不依赖洞内内容
    decoy_min: int = 1  # 伪缺口数量下限（0=禁用伪缺口）
    decoy_max: int = 2


@dataclass
class RenderResult:
    """渲染产物。decoys 坐标仅供测试断言，绝不进响应或封存载荷。"""

    bg: Image.Image  # RGB (width, height)
    slider: Image.Image  # RGBA (size, size)，alpha=旋转后形状遮罩，非形状区透明
    hole_mask: Image.Image  # L (size, size)：真缺口/伪缺口/拼图块共用的旋转后遮罩
    tints: list[tuple[int, int, int]]  # [0]=真缺口色调（=拼图块色调），其余=伪缺口色调（洗牌后分配）
    decoys: list[tuple[int, int]]  # 伪缺口画布坐标（y 恒等于 target_y——同行不变式）


def build_puzzle_mask(shape: str, size: int, theta: float, rng: random.Random) -> Image.Image:
    """按形状绘制遮罩并旋转：返回 L 模式 (size, size)，形状区 255、其余 0。

    4× 超采样绘制 → 旋转（BICUBIC）→ LANCZOS 缩回，边缘平滑且形状/旋转角
    与拼图块、真伪缺口完全一致（单实例，后续全部复用）。
    """
    ss = size * _SUPERSAMPLE
    canvas = Image.new("L", (ss, ss), 0)
    draw = ImageDraw.Draw(canvas)
    if shape == "rounded":
        inset = 0  # 与 legacy 圆角方一致：占满画布
        draw.rounded_rectangle(
            [inset, inset, ss - 1 - inset, ss - 1 - inset],
            radius=8 * _SUPERSAMPLE,
            fill=255,
        )
    elif shape == "knob":
        # 拼图凸舌形：内缩方体 + 单侧圆凸舌；凸舌收在 ±8° 旋转的安全半径内
        # （44px 刻度：体 [5,39]、凸舌半径 5、圆心距画布中心 ≤ 16+5 < 22）
        body = 5 * _SUPERSAMPLE
        draw.rounded_rectangle([body, body, ss - body, ss - body], radius=8 * _SUPERSAMPLE, fill=255)
        tab_r = 5 * _SUPERSAMPLE
        side = rng.choice(("up", "down", "left", "right"))
        mid = ss // 2
        centers = {
            "up": (mid, body),
            "down": (mid, ss - body),
            "left": (body, mid),
            "right": (ss - body, mid),
        }
        cx, cy = centers[side]
        draw.ellipse([cx - tab_r, cy - tab_r, cx + tab_r, cy + tab_r], fill=255)
    elif shape == "circle":
        r = ss // 2 - _SUPERSAMPLE  # 留 1px（44 刻度）余量防旋转裁边
        draw.ellipse([ss // 2 - r, ss // 2 - r, ss // 2 + r, ss // 2 + r], fill=255)
    elif shape == "capsule":
        # 横向胶囊：左右缘触达画布边（保持「缺口占满横向行程带」的视觉语义）
        half_h = 15 * _SUPERSAMPLE // 2 * 2  # 偶数高度，radius=高/2 成标准 stadium
        top = (ss - half_h) // 2
        draw.rounded_rectangle([0, top, ss - 1, top + half_h], radius=half_h // 2, fill=255)
    else:  # pragma: no cover - 注册表守卫
        raise ValueError(f"未知拼图形状: {shape}")
    rotated = canvas.rotate(theta, resample=Image.BICUBIC, fillcolor=0)
    return rotated.resize((size, size), Image.LANCZOS)


def hue_shift(img: Image.Image, delta: int) -> Image.Image:
    """RGB 色相偏移：H 带 (v+delta) mod 256 一次 LUT 查表（环形色相），无需 numpy。"""
    hsv = img.convert("HSV")
    h, s, v = hsv.split()
    h = h.point(lambda value: (value + delta) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _clamp_gain(mean_level: float, gain: float) -> float:
    """亮度增益按源区均值钳制，防止浅色底 ×增益 截断抹平内容。"""
    if mean_level <= 0:
        return gain
    return min(gain, 250.0 / mean_level)


def perturb_piece(img: Image.Image, rng: random.Random, params: RenderParams) -> Image.Image:
    """拼图块内容扰动：缩放抖动 → 亮度（钳制防削顶）→ 对比度 → 色相。"""
    w, h = img.size
    # 内容缩放抖动：居中裁 1/factor 区域再放回原尺寸（轮廓在外层按遮罩裁，不受影响）
    factor = rng.uniform(1 - params.scale, 1 + params.scale)
    cw = max(8, round(w / factor))
    ch = max(8, round(h / factor))
    left = (w - cw) // 2
    top = (h - ch) // 2
    result = img.crop((left, top, left + cw, top + ch)).resize((w, h), Image.BICUBIC)

    grayscale_mean = ImageStat.Stat(result.convert("L")).mean[0]
    gain = _clamp_gain(grayscale_mean, rng.uniform(1 - params.brightness, 1 + params.brightness))
    result = ImageEnhance.Brightness(result).enhance(gain)
    result = ImageEnhance.Contrast(result).enhance(rng.uniform(1 - params.contrast, 1 + params.contrast))
    result = hue_shift(result, rng.randint(-params.hue_shift, params.hue_shift))
    if params.noise_sigma > 0:
        # 独立高频噪声：拼图块专属的逐像素扰动（ImageChops.add 逐通道饱和截断，可接受）
        noise = Image.merge(
            "RGB",
            tuple(Image.effect_noise((w, h), params.noise_sigma) for _ in range(3)),
        )
        result = ImageChops.add(result, noise, scale=1.0, offset=-128)
    return result


def pick_tints(rng: random.Random, count: int) -> list[tuple[int, int, int]]:
    """判别色调调色板：色相均布无碰撞、明度逐档错开（两两可分，色觉障碍用户可按明度
    区分候选），**生成后随机洗牌**——真/伪分配与明度次序解绑（验收 S7：洗牌前
    「掩码内均值明度 argmax」99.2% 命中，真缺口恒为 tints[0]=最亮档）。

    §18.7 可用性修复：饱和度取 0.95（初版 0.55 + alpha 52 + 调制下限 0.25× 的组合
    令洞内有效色度低至 ~13/255，人眼无法完成「拼图块↔缺口」的跨亮度基线色调匹配）。
    色调是本方案唯一判别通道，必须**高饱和呈现**才有讨论机器可读性的资格。

    无障碍性不受损：拼图块与真缺口恒为同一色调，匹配依据是「色调相等」而非
    「明度排序」；明度错开只承担「候选两两可分」，不承担「指认真缺口」。"""
    start = rng.randint(0, 255)
    tints: list[tuple[int, int, int]] = []
    for index in range(count):
        hue = (start + index * 256 // max(1, count)) % 256
        value = 235 - index * 40  # 明度错开兜底（40 档间隔 > 同档噪声扰动幅度）
        r, g, b = colorsys.hsv_to_rgb(hue / 255.0, 0.95, max(120, value) / 255.0)
        tints.append((round(r * 255), round(g * 255), round(b * 255)))
    rng.shuffle(tints)
    return tints


def layout_decoys(
    rng: random.Random,
    target: tuple[int, int],
    count: int,
    puzzle_size: int,
    width: int,
) -> list[tuple[int, int]]:
    """伪缺口布局（拒绝采样）：**与真缺口同行**，仅沿 x 轴分离。

    两条不变式（验收 S3 二次修复）：
    - **同行**：y 恒等于 target_y——sliderY（=target_y）随响应公开且校验只比 x，
      伪缺口若异行，「锚点 y 最接近 sliderY」即成确定性指路标（验收方浏览器实测
      96.7% 命中）。同行后该判据退化为在候选中随机。
    - **x 轴分离**：|dx − target_x| 及两两 |dx| ≥ puzzle_size + 20——校验只比 x，
      伪缺口若落进 x 容差带，选错反而「白拿通过」，烧票机制失效（> 容差 12 的 5 倍）。
    采样失败时降级减少伪缺口数（防御性兜底，正常参数下不会触发）。"""
    if count <= 0:
        return []
    min_gap = puzzle_size + _DECOY_MIN_GAP_EXTRA
    x_low, x_high = 8, width - puzzle_size - 8
    if x_high < x_low:
        return []

    decoys: list[tuple[int, int]] = []
    for _ in range(count):
        for _attempt in range(50):
            x = rng.randint(x_low, x_high)
            if abs(x - target[0]) < min_gap:
                continue
            if any(abs(x - d[0]) < min_gap for d in decoys):
                continue
            decoys.append((x, target[1]))
            break
    return decoys


def render_slider_captcha(
    width: int,
    height: int,
    target_x: int,
    target_y: int,
    puzzle_size: int,
    *,
    rng: random.Random | None = None,
    params: RenderParams = RenderParams(),
) -> RenderResult:
    """加固渲染管线：单实例遮罩咬合 + 拼图块内容扰动 + 真伪缺口色调判别。"""
    rng = rng if rng is not None else random.Random()

    # ── 阶段 1：形状与遮罩（三方共用，咬合由构造保证）──
    theta = rng.uniform(3.0, max(3.0, params.rotate_deg)) * rng.choice((-1, 1))
    shape = rng.choice(PUZZLE_SHAPES)
    hole_mask = build_puzzle_mask(shape, puzzle_size, theta, rng)

    decoy_count = rng.randint(max(0, params.decoy_min), max(0, params.decoy_max))
    decoys = layout_decoys(rng, (target_x, target_y), decoy_count, puzzle_size, width)
    tints = pick_tints(rng, 1 + len(decoys))
    true_tint = tints[0]

    # ── 阶段 2：背景（中灰底 + 随机噪声线）──
    # 背景亮度刻意取 100-160（legacy 为 180-230 浅色）：§13 求解器的亮度补偿
    # （×255/145）会把浅色背景饱和成一片 255 白场，洞成为全图唯一暗结构——
    # 求解器退化为「暗块探测器」且必然命中。中灰背景下补偿不饱和，结构化信号消失。
    bg = Image.new("RGB", (width, height), _random_bg_color(rng))
    draw = ImageDraw.Draw(bg)
    for _ in range(60):
        draw.line(
            [
                rng.randint(0, width),
                rng.randint(0, height),
                rng.randint(0, width),
                rng.randint(0, height),
            ],
            fill=_random_bg_color(rng),
            width=1,
        )

    # ── 阶段 3：拼图块（必须在 overlay 合成前裁剪——缺口暗块不得进入拼图块）──
    # 关键：拼图块以「补偿后寄存器」呈现（×255/145，即 §13 求解器对背景施加的同一
    # 亮度还原）。寄存器对齐分析（§17 基准实证迭代）：
    #   补偿后背景场域 ≈ bg×1.76（中灰 100-160 → 176-282 截断）；补偿后暗洞 ≈
    #   0.57×bg×1.76 ≈ bg 原始亮度。若拼图块取原始寄存器（≈bg），其亮度恰与暗洞
    #   重合 → 求解器的滑窗 MAD 把洞判为最佳匹配（暗块探测器，§13 实测 86-90% 命中
    #   的真实机制）。取补偿寄存器后拼图块≈场域亮度，洞被双向排斥，argmin 只能
    #   在场域内随噪声线游走——答案不再可由任何亮度/内容寄存器定位。
    # 真人侧：拼图块是明亮的悬浮块（轮廓+色调判别不受影响），观感清晰。
    pad = _ROTATE_PAD // 2
    src = bg.crop((target_x - pad, target_y - pad, target_x + puzzle_size + pad, target_y + puzzle_size + pad))
    src = Image.merge("RGB", tuple(band.point(_COMPENSATE_LUT) for band in src.split()))
    src = perturb_piece(src, rng, params)
    piece = src.convert("RGBA").crop((pad, pad, pad + puzzle_size, pad + puzzle_size))
    piece.putalpha(hole_mask)  # 轮廓=旋转后形状遮罩 → 画布恒 size×size，非形状区透明
    # 拼图块染色（§18.7）：单缺口模式取 0——拼图块一旦高饱和染色，其平坦色调与洞内
    # 平坦色调在 RGB 空间直接相似，§13 求解器无需内容信息即可模板命中（实测 100%）；
    # 判别模式（伪缺口启用）跟随 tint_alpha，人眼靠「拼图块↔缺口同色」完成任务。
    piece_alpha = params.tint_alpha if params.piece_tint_alpha is None else params.piece_tint_alpha
    if piece_alpha > 0:
        piece = _alpha_blend_masked(piece, true_tint, hole_mask, piece_alpha)
    piece.putalpha(hole_mask)  # 终末钳制：alpha 恒等于遮罩，构造性保证逐字节咬合

    # ── 阶段 4：真缺口 + 伪缺口（同遮罩/噪声统计/同行，仅色调互异）──
    # 形状/旋转/暗块样式在真假缺口间**构造性一致**：任何「互异保证」（异形、异行、
    # 明度排序）都是给比较器留的确定性信号（验收 S3/S6/S7）。唯一判别通道=色调相等。
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    true_mean = _hole_noise_mean(bg, target_x, target_y, puzzle_size)
    paste_hole(
        overlay,
        target_x,
        target_y,
        true_tint,
        hole_mask,
        params.tint_alpha,
        params.hole_noise_sigma,
        true_mean,
        rng,
    )
    for index, (dx, dy) in enumerate(decoys):
        decoy_mean = _hole_noise_mean(bg, dx, dy, puzzle_size)
        paste_hole(
            overlay,
            dx,
            dy,
            tints[1 + index],
            hole_mask,
            params.tint_alpha,
            params.hole_noise_sigma,
            decoy_mean,
            rng,
        )
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    return RenderResult(bg=bg, slider=piece, hole_mask=hole_mask, tints=tints, decoys=decoys)


def paste_hole(
    overlay: Image.Image,
    x: int,
    y: int,
    tint: tuple[int, int, int],
    hole_mask: Image.Image,
    tint_alpha: int,
    noise_sigma: int = 0,
    noise_mean: int = 75,
    rng: random.Random | None = None,
) -> None:
    """在 overlay 上烧一个缺口：暗块 → 洞内噪声替换（均值≈0.57×局部亮度）→ 判别色调。

    洞内替换的两大作用（§17 基准实证）：
    - 内容_destroyed：「洞内=原图×常数」的补偿还原关系不复存在；
    - 均值取暗块自然亮度：避免洞内成为补偿后唯一「非白结构」（背景过浅时
      补偿饱和成白场，洞即暗块探测器信标——这正是 §13 求解器实际依赖的信号）。"""
    size = hole_mask.size
    dark = Image.new("RGBA", size, (0, 0, 0, _HOLE_DARK_ALPHA))
    overlay.paste(dark, (x, y), hole_mask)
    if noise_sigma > 0:
        shift = noise_mean - 128
        noise = Image.merge(
            "RGB",
            tuple(Image.effect_noise(size, noise_sigma).point(lambda v: min(255, max(0, v + shift))) for _ in range(3)),
        ).convert("RGBA")
        noise.putalpha(hole_mask)
        overlay.alpha_composite(noise, (x, y))
    if tint_alpha > 0:
        # 色调 alpha 逐像素随机调制（下限 0.70×）：hue 方向不变（真人按色相方向判别，
        # 无感），破坏「拼图块恒定偏移 vs 洞内恒定偏移在真位互相抵消」的加性模型；
        # 下限刻意取 0.70 而非 0.25——调制会把有效色度压到人眼不可辨（§18.7 教训）
        mod = Image.effect_noise(size, 128).point(lambda v: 178 + v // 4)  # ≈0.70-0.95 倍
        modulated_alpha = ImageChops.multiply(hole_mask.point(lambda v: v * tint_alpha // 255), mod)
        layer = Image.new("RGBA", size, (*tint, 0))
        layer.putalpha(modulated_alpha)
        overlay.alpha_composite(layer, (x, y))


def _random_bg_color(rng: random.Random) -> tuple[int, int, int]:
    """中性灰（三通道同值，100-160，legacy 为 180-230 浅色）。

    真实目的：§13 求解器的亮度反向补偿（×1.76）会把浅色背景整体饱和成 255 白场，
    使洞成为全图唯一暗结构、求解器退化为暗块探测器；中灰下补偿不饱和，该信号消失。
    （勘误史：早期注释「防 OCR 定位缺口」不成立——压暗背景与可定位性无关。多缺口
    判别模式下「定位不是难点、区分真假才是」；单缺口模式下定位即答案、亮度/色度
    定位器恒 100%（§19 既知终态），压暗仅服务于打断补偿还原，不构成定位防御。）
    三通道必须同值（§18.7）：通道独立随机会让背景自带色度（S 可达 96），既污染
    唯一判别通道（高饱和色调）的信噪比，也让色度分割无从下手。"""
    value = rng.randint(100, 160)
    return (value, value, value)


def _hole_noise_mean(bg: Image.Image, x: int, y: int, size: int) -> int:
    """洞内噪声目标均值 ≈ 0.57×局部背景亮度（暗块叠加的自然结果），保持洞的暗块观感。"""
    region = bg.crop((x, y, x + size, y + size)).convert("L")
    return int(ImageStat.Stat(region).mean[0] * (255 - _HOLE_DARK_ALPHA) / 255)


def _masked_alpha(mask: Image.Image, alpha: int) -> Image.Image:
    return mask.point(lambda value: value * alpha // 255)


def _alpha_blend_masked(
    base: Image.Image,
    color: tuple[int, int, int],
    mask: Image.Image,
    alpha: int,
) -> Image.Image:
    """以 mask 为范围、alpha 为不透明度，把颜色叠加到 RGBA 图像上（返回新图）。"""
    layer = Image.new("RGBA", base.size, (*color, 0))
    layer.putalpha(_masked_alpha(mask, alpha))
    return Image.alpha_composite(base, layer)
