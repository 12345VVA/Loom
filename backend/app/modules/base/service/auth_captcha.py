"""验证码域（AuthService 的 captcha 分域 mixin）：滑块图生成与轨迹校验。"""

from __future__ import annotations

import json
import re
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.base.model.auth import CaptchaResponse
from app.modules.base.service.cache_service import cache_get_del, cache_set

# captcha 参数校验范围
CAPTCHA_WIDTH_MIN = 80
CAPTCHA_WIDTH_MAX = 300
CAPTCHA_HEIGHT_MIN = 80
CAPTCHA_HEIGHT_MAX = 300
_CAPTCHA_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


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

    def captcha(self, width: int = 150, height: int = 80, color: str = "#333333") -> CaptchaResponse:
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
        puzzle_size = 44
        max_target = width_int - puzzle_size - 8
        if max_target <= 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"验证码宽度需大于 {puzzle_size + 16}",
            )
        target_x = 8 + secrets.randbelow(max_target - 8 + 1)
        target_y = (height_int - puzzle_size) // 2

        bg_image, slider_image = self._render_captcha_images(width_int, height_int, target_x, target_y, puzzle_size)

        captcha_id = uuid4().hex
        cache_set(
            self._build_captcha_cache_key(captcha_id),
            json.dumps(
                {
                    "type": "slider",
                    "target_x": target_x,
                    "tolerance": tolerance,
                    "created_at": int(time.time() * 1000),
                },
                ensure_ascii=True,
            ),
            settings.CAPTCHA_EXPIRE_SECONDS,
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

    def captcha_check(self, captcha_id: str | None, verify_code: str | None) -> None:
        if not captcha_id or not verify_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不能为空")
        cache_key = self._build_captcha_cache_key(captcha_id)
        # 防重放：原子读取并删除（GETDEL），并发请求中仅一个能消费成功
        cached = cache_get_del(cache_key)
        if not cached:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        try:
            challenge = json.loads(cached)
            payload = json.loads(verify_code)
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        if challenge.get("type") != "slider":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        try:
            target_x = float(challenge["target_x"])
            tolerance = float(challenge["tolerance"])
            final_x = float(payload["x"])
            duration_ms = int(payload["duration"])
            track = payload["track"]
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

        if abs(final_x - target_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")
        if duration_ms < settings.CAPTCHA_SLIDER_MIN_DURATION_MS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证速度过快，请重试")
        if not isinstance(track, list) or len(track) < settings.CAPTCHA_SLIDER_MIN_TRACK_POINTS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")

        previous_x = -1.0
        backtrack_total = 0.0
        for point in track:
            if not isinstance(point, dict):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            try:
                current_x = float(point["x"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            if current_x < previous_x:
                backtrack = previous_x - current_x
                backtrack_total += backtrack
                if backtrack > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
            previous_x = current_x

        if backtrack_total > settings.CAPTCHA_SLIDER_MAX_BACKTRACK_PX * 2:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")
        if abs(previous_x - final_x) > tolerance:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码轨迹异常")

    @staticmethod
    def _build_captcha_cache_key(captcha_id: str) -> str:
        return f"verify:slider:{captcha_id}"
