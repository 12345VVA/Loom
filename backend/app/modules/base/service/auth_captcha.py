"""验证码域（AuthService 的 captcha 分域 mixin）：滑块图生成与轨迹校验。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import secrets
import time
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.base.model.auth import CaptchaResponse
from app.modules.base.service.cache_service import cache_get_del, cache_incr, cache_set

# captcha 参数校验范围（仅作入参契约校验；渲染与答案解空间由服务端固定尺寸决定，见 C2）
CAPTCHA_WIDTH_MIN = 80
CAPTCHA_WIDTH_MAX = 300
CAPTCHA_HEIGHT_MIN = 80
CAPTCHA_HEIGHT_MAX = 300
# 服务端固定渲染尺寸：客户端 width 曾直接决定答案解空间（width=80 仅 21 个候选位、
# 配合 ±12 容差存在万能 x，即报告 C2），前端本就上报 300×120，服务端不再信任该参数
CAPTCHA_RENDER_WIDTH = 300
CAPTCHA_RENDER_HEIGHT = 120
# 解空间不变式：候选位置数必须 ≥ 10×容差带宽度，否则验证码可被万能 x 枚举（配置错误快速失败）
_CANDIDATE_BAND_RATIO = 10
_PUZZLE_SIZE = 44
_CAPTCHA_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    """由 JWT 密钥派生 Fernet（答案封存用，M3：Redis 明文遍历即得全部答案）。"""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest())
    return Fernet(key)


def _seal_challenge(payload: dict) -> str:
    """签发载荷封存为密文——Redis 侧只见 HMAC 包裹的密文，防「读缓存即知答案」。"""
    return _fernet().encrypt(json.dumps(payload, ensure_ascii=True).encode()).decode()


def _unseal_challenge(raw: str) -> dict | None:
    """解封校验载荷；密文被篡改/非密文/解析失败一律返回 None（调用方统一 401）。"""
    try:
        challenge = json.loads(_fernet().decrypt(raw.encode()))
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return challenge if isinstance(challenge, dict) else None


def _reject_non_finite_constant(value: str) -> float:
    """json.loads 的 parse_constant 钩子：拒绝 NaN/Infinity/-Infinity（C1）。

    IEEE-754 下任何与 NaN 的数值比较恒为 False，位置/轨迹校验会被整体短路；
    JSON 规范本就不含这些常量，Python 默认 allow_nan 属于方言宽容，此处收紧。
    """
    logger.warning("验证码校验拒绝：verify_code 含非法数值常量 %s（疑似绕过尝试，L4）", value)
    raise ValueError(f"非法数值常量: {value}")


class CaptchaMixin:
    """滑块验证码签发与校验。依赖宿主提供 `self.session`。"""

    @staticmethod
    def _random_light_color(rng) -> tuple[int, int, int]:
        """浅色随机背景色（验证码底色，配合噪声线条防 OCR 轻易定位缺口）。"""
        return (rng.randint(180, 230), rng.randint(180, 230), rng.randint(180, 230))

    @staticmethod
    def _image_to_data_url(img) -> str:
        """PIL 图像转 data URL（PNG base64）。"""
        import base64
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def _render_captcha_images(self, width: int, height: int, target_x: int, target_y: int, puzzle_size: int):
        """生成带缺口的背景图与滑块拼图块。缺口位置即答案，但不以数值返回前端。"""
        import random

        from PIL import Image, ImageDraw

        rng = random.Random()
        # 背景：浅色 + 随机噪声线条，避免纯色下缺口过于醒目
        bg = Image.new("RGB", (width, height), self._random_light_color(rng))
        draw = ImageDraw.Draw(bg)
        for _ in range(60):
            draw.line(
                [
                    rng.randint(0, width),
                    rng.randint(0, height),
                    rng.randint(0, width),
                    rng.randint(0, height),
                ],
                fill=self._random_light_color(rng),
                width=1,
            )
        # 滑块 = 裁剪缺口位置的背景内容（真正的拼图块），用户拖它对齐缺口
        slider = bg.crop((target_x, target_y, target_x + puzzle_size, target_y + puzzle_size)).convert("RGBA")
        # 在背景挖缺口：半透明暗块 + 描边，提示拼合位置
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rounded_rectangle(
            [target_x, target_y, target_x + puzzle_size, target_y + puzzle_size],
            radius=8,
            fill=(0, 0, 0, 110),
            outline=(255, 255, 255, 220),
            width=2,
        )
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
        # 滑块加描边，拖动时与背景区分
        sdraw = ImageDraw.Draw(slider)
        sdraw.rounded_rectangle(
            [0, 0, puzzle_size - 1, puzzle_size - 1],
            radius=8,
            outline=(40, 40, 40, 255),
            width=2,
        )
        return bg, slider

    def captcha(
        self, width: int = 150, height: int = 80, color: str = "#333333", *, client_ip: str | None = None
    ) -> CaptchaResponse:
        # M1：签发限流（中间件 30/min/IP 之外的长窗口上限，抬升分布式图像生成拖垮 CPU 的成本）
        issue_ip = client_ip or "unknown"
        issued = cache_incr(f"captcha:issue:{issue_ip}", settings.CAPTCHA_ISSUE_WINDOW_SECONDS)
        if issued is not None and issued > settings.CAPTCHA_ISSUE_MAX_PER_WINDOW:
            logger.warning("验证码签发限流触发 ip=%s issued=%d（M1/L4）", issue_ip, issued)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="验证码获取过于频繁，请稍后再试")

        # 参数范围校验，防止恶意输入
        try:
            width_int = int(width)
            height_int = int(height)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="width/height 必须为整数")
        if not (CAPTCHA_WIDTH_MIN <= width_int <= CAPTCHA_WIDTH_MAX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"width 必须在 {CAPTCHA_WIDTH_MIN}-{CAPTCHA_WIDTH_MAX} 之间",
            )
        if not (CAPTCHA_HEIGHT_MIN <= height_int <= CAPTCHA_HEIGHT_MAX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"height 必须在 {CAPTCHA_HEIGHT_MIN}-{CAPTCHA_HEIGHT_MAX} 之间",
            )
        if not _CAPTCHA_COLOR_PATTERN.match(color or ""):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="color 必须为 #RRGGBB 格式的十六进制颜色",
            )

        tolerance = settings.CAPTCHA_SLIDER_TOLERANCE
        # C2 修复：渲染与答案解空间一律使用服务端固定尺寸，客户端 width/height 不再参与
        width_int = CAPTCHA_RENDER_WIDTH
        height_int = CAPTCHA_RENDER_HEIGHT
        puzzle_size = _PUZZLE_SIZE
        max_target = width_int - puzzle_size - 8
        if max_target <= 8:
            # 服务端固定尺寸下不应触发；防配置/常量被误改导致解空间为空
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="验证码渲染尺寸配置非法",
            )
        # 解空间不变式守卫（C2 纵深）：候选位置数 < 10×容差带时，存在对任意 target_x
        # 恒命中的万能 x 区间——拒绝签发而非退化出可枚举的验证码
        if (max_target - 8 + 1) < _CANDIDATE_BAND_RATIO * (2 * tolerance):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="验证码配置解空间不足（CAPTCHA_SLIDER_TOLERANCE 与渲染尺寸配比失衡）",
            )
        target_x = 8 + secrets.randbelow(max_target - 8 + 1)
        # L3：缺口纵向位置随机化（原恒为居中，降低模式识别价值）；前端经 sliderY 响应驱动
        target_y = secrets.randbelow(height_int - puzzle_size + 1)

        bg_image, slider_image = self._render_captcha_images(width_int, height_int, target_x, target_y, puzzle_size)

        captcha_id = uuid4().hex
        # M3：答案封存为密文（Redis 明文遍历曾可直接读出全部 target_x）；
        # M4：fail-closed——生产 Redis 不可用时不降级进程内缓存（多进程互不共享，
        # 会产生「永远错」的 captchaId），明确 503 而非静默生成必失效验证码
        sealed = _seal_challenge(
            {
                "type": "slider",
                "target_x": target_x,
                "tolerance": tolerance,
                "created_at": int(time.time() * 1000),
                "bind_ip": client_ip,  # L3：绑定签发 IP，提交时不一致即拒
            }
        )
        if not cache_set(
            self._build_captcha_cache_key(captcha_id),
            sealed,
            settings.CAPTCHA_EXPIRE_SECONDS,
            allow_memory_fallback=settings.DEBUG,
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="验证码服务暂不可用，请稍后重试",
            )
        # 不返回 targetX（答案）：仅返回带缺口的背景图与滑块图，前端视觉对齐
        return CaptchaResponse(
            captcha_id=captcha_id,
            data={
                "type": "slider",
                "bg": self._image_to_data_url(bg_image),
                "slider": self._image_to_data_url(slider_image),
                "sliderWidth": puzzle_size,
                "sliderY": target_y,
                "trackWidth": width_int,
                "tolerance": tolerance,
                "expireSeconds": settings.CAPTCHA_EXPIRE_SECONDS,
                "label": "拖动滑块对齐缺口完成验证",
            },
        )

    def captcha_check(self, captcha_id: str | None, verify_code: str | None, *, client_ip: str | None = None) -> None:
        if not captcha_id or not verify_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        cache_key = self._build_captcha_cache_key(captcha_id)
        # 防重放：原子读取并删除（GETDEL），并发请求中仅一个能消费成功
        cached = cache_get_del(cache_key)
        if not cached:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        challenge = _unseal_challenge(cached)
        if challenge is None or challenge.get("type") != "slider":
            # 密文篡改/非密文/非法形态统一 401（L1）
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        # L3：签发 IP 绑定校验（双方均已知时才比对，兼容旧缓存与无 request 场景）
        bound_ip = challenge.get("bind_ip")
        if bound_ip and client_ip and bound_ip != client_ip:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        try:
            # parse_constant 拒绝 NaN/Infinity（C1）：json.loads 默认 allow_nan=True，
            # '{"x": NaN}' 会解析成 float('nan') 使下方全部比较恒为 False
            payload = json.loads(verify_code, parse_constant=_reject_non_finite_constant)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        try:
            target_x = float(challenge["target_x"])
            tolerance = float(challenge["tolerance"])
            final_x = float(payload["x"])
            duration_ms = int(payload["duration"])
            track = payload["track"]
        except (KeyError, TypeError, ValueError, OverflowError):
            # OverflowError：1e999 这类字面量绕过 parse_constant 解析为 inf，int(inf) 抛溢出
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        # C1 纵深：非有限值（含缓存被写坏的场景）直接拒绝，位置/轨迹比较不允许退化
        if not (math.isfinite(target_x) and math.isfinite(tolerance) and math.isfinite(final_x)):
            logger.warning("验证码校验拒绝：入参含非有限值（final_x=%r，疑似绕过尝试，L4）", final_x)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        if abs(final_x - target_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if duration_ms < settings.CAPTCHA_SLIDER_MIN_DURATION_MS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        # H1：自报拖拽时长不得超过验证码时效窗口（拖 10 分钟再提交属伪造载荷）
        if duration_ms > settings.CAPTCHA_EXPIRE_SECONDS * 1000:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        # M2：轨迹点数上限（防数 MB JSON + 数十万点占用工作线程 CPU/内存）
        if not isinstance(track, list) or len(track) < settings.CAPTCHA_SLIDER_MIN_TRACK_POINTS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if len(track) > settings.CAPTCHA_SLIDER_MAX_TRACK_POINTS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        # H1：轨迹时间轴交叉校验——前端 t 与 duration 同源（Date.now 差值），要求
        # 非负、单调非递减、末点不超过自报时长（+事件循环余量）、时长与末点间隔有界。
        # 定位是弱防护（脚本可伪造一致时间轴），强度来自一次性消费+失败锁定+限流的叠加。
        previous_x = -1.0
        previous_t = -1
        backtrack_total = 0.0
        for point in track:
            if not isinstance(point, dict):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
            try:
                current_x = float(point["x"])
                current_t = int(point["t"])
            except (KeyError, TypeError, ValueError, OverflowError):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
            if not math.isfinite(current_x):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
            if current_t < 0 or current_t < previous_t:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
            previous_t = current_t
            if current_x < previous_x:
                backtrack = previous_x - current_x
                backtrack_total += backtrack
                if backtrack > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
            previous_x = current_x

        if backtrack_total > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX * 2:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if abs(previous_x - final_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        # H1：末点时刻不得超过自报时长（同源时钟，200ms 为事件循环余量）；
        # 时长与末点间隔过大说明轨迹与 duration 各自编造
        if previous_t > duration_ms + 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if duration_ms - previous_t > settings.CAPTCHA_SLIDER_MAX_RELEASE_GAP_MS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

    @staticmethod
    def _build_captcha_cache_key(captcha_id: str) -> str:
        return f"verify:slider:{captcha_id}"
