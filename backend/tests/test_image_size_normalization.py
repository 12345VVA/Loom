"""生图尺寸入参归一化与真实尺寸探测的回归测试。

背景（2026-09-21 事故）
-----------------------
工作流生图节点里填的 `864×1152` 用的是**全角乘号 U+00D7**（不是 ASCII `x`）。
ToAPIs 适配器用 `"x" in size` 判定，命中失败后**静默回落**成 `1024x1024`，
全程无报错无日志，问题隐藏了一整天才被发现。

本文件把当时的取证结论固化成防线：

1. 各类易错乘号字符（全角/数学符号/形近字母）必须被归一化
2. 非法尺寸必须**显式报错**，不再静默回落
3. 落盘时从图片字节探测真实宽高，并对「请求尺寸 vs 实际产出」不一致告警
"""

from __future__ import annotations

import struct
import unittest

from fastapi import HTTPException

from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.ai.service.adapters.factory import (
    _normalize_bailian_image_size,
    _validate_seedream_4_size,
)
from app.modules.ai.service.adapters.size_utils import (
    ensure_pixel_size,
    normalize_size_token,
    parse_pixel_size,
)
from app.modules.ai.service.adapters.toapis import _convert_pixel_size_to_ratio_and_resolution
from app.modules.media.service.media_service import _probe_image_dimensions, _requested_image_size

FULLWIDTH_MULTIPLY = chr(0xD7)


class SizeTokenNormalizationTest(unittest.TestCase):
    """size_utils.normalize_size_token —— 字符归一化。"""

    def test_ascii_passthrough(self) -> None:
        self.assertEqual(normalize_size_token("864x1152"), "864x1152")

    def test_fullwidth_multiply_sign(self) -> None:
        """本次事故的主角：U+00D7 与 ASCII x 肉眼无法区分。"""
        self.assertEqual(normalize_size_token("864" + FULLWIDTH_MULTIPLY + "1152"), "864x1152")

    def test_other_multiplication_signs(self) -> None:
        for ch in ("\u2a2f", "\u2715", "\u2716", "\u2a09", "\u2573", "\u0445", "\u03a7"):
            with self.subTest(char=hex(ord(ch))):
                self.assertEqual(normalize_size_token("864" + ch + "1152"), "864x1152")

    def test_uppercase_and_asterisk_and_spaces(self) -> None:
        self.assertEqual(normalize_size_token("864X1152"), "864x1152")
        self.assertEqual(normalize_size_token("864*1152"), "864x1152")
        self.assertEqual(normalize_size_token(" 864 x 1152 "), "864x1152")

    def test_fullwidth_digits(self) -> None:
        self.assertEqual(normalize_size_token("８６４ｘ１１５２"), "864x1152")

    def test_ratio_untouched(self) -> None:
        self.assertEqual(normalize_size_token("3:4"), "3:4")
        self.assertEqual(normalize_size_token(" 3 : 4 "), "3:4")

    def test_empty_values(self) -> None:
        self.assertIsNone(normalize_size_token(None))
        self.assertIsNone(normalize_size_token("   "))


class ParsePixelSizeTest(unittest.TestCase):
    """size_utils.parse_pixel_size —— 像素解析。"""

    def test_valid(self) -> None:
        self.assertEqual(parse_pixel_size("864x1152"), (864, 1152))
        self.assertEqual(parse_pixel_size("864" + FULLWIDTH_MULTIPLY + "1152"), (864, 1152))

    def test_invalid(self) -> None:
        for value in ("3:4", "abc", "0x100", "100000x100", "1024x", None, ""):
            with self.subTest(value=value):
                self.assertIsNone(parse_pixel_size(value))


class EnsurePixelSizeTest(unittest.TestCase):
    """size_utils.ensure_pixel_size —— 未提供走默认，非法必须报错。"""

    def test_missing_falls_back_to_default(self) -> None:
        """未提供是合法场景，走默认值——这不是静默吞错。"""
        self.assertEqual(ensure_pixel_size(None), "1024x1024")
        self.assertEqual(ensure_pixel_size(""), "1024x1024")

    def test_fullwidth_is_normalized_not_silently_dropped(self) -> None:
        """核心回归点：全角输入应被纠正成所填尺寸，而不是被换成默认值。"""
        self.assertEqual(ensure_pixel_size("864" + FULLWIDTH_MULTIPLY + "1152"), "864x1152")

    def test_valid_passthrough(self) -> None:
        self.assertEqual(ensure_pixel_size("1536x2048"), "1536x2048")

    def test_invalid_raises(self) -> None:
        """核心回归点：非法尺寸必须报错，不能静默回落。"""
        for value in ("3:4", "large", "1024x", "hugexbig"):
            with self.subTest(value=value):
                with self.assertRaises(UpstreamApiError):
                    ensure_pixel_size(value)


class ToApisSizeHandlingTest(unittest.TestCase):
    """toapis 适配器的尺寸换算与报错。"""

    def test_defaults(self) -> None:
        self.assertEqual(_convert_pixel_size_to_ratio_and_resolution(None), ("1:1", "1K"))

    def test_ratio_passthrough(self) -> None:
        self.assertEqual(_convert_pixel_size_to_ratio_and_resolution("3:4"), ("3:4", "1K"))

    def test_pixel_conversion(self) -> None:
        self.assertEqual(_convert_pixel_size_to_ratio_and_resolution("1024x1024"), ("1:1", "1K"))
        self.assertEqual(_convert_pixel_size_to_ratio_and_resolution("1728x2304"), ("3:4", "2K"))

    def test_fullwidth_is_accepted(self) -> None:
        """旧实现下这里会静默变成 1:1——正是本次事故。"""
        self.assertEqual(
            _convert_pixel_size_to_ratio_and_resolution("864" + FULLWIDTH_MULTIPLY + "1152"),
            ("3:4", "1K"),
        )

    def test_invalid_raises_instead_of_falling_back(self) -> None:
        with self.assertRaises(UpstreamApiError):
            _convert_pixel_size_to_ratio_and_resolution("big")


class BaolianAndVolcengineSizeTest(unittest.TestCase):
    """百炼与火山链路也曾用同一套字符判定，一并回归。"""

    def test_bailian_uses_asterisk_form(self) -> None:
        self.assertEqual(_normalize_bailian_image_size("1024x1024"), "1024*1024")
        self.assertEqual(_normalize_bailian_image_size("1024*1024"), "1024*1024")
        # 旧实现下全角会原样透传给上游
        self.assertEqual(_normalize_bailian_image_size("864" + FULLWIDTH_MULTIPLY + "1152"), "864*1152")

    def test_bailian_leaves_non_pixel_values_alone(self) -> None:
        self.assertEqual(_normalize_bailian_image_size("1K"), "1K")
        self.assertEqual(_normalize_bailian_image_size(None), None)

    def test_seedream_min_pixel_enforced(self) -> None:
        _validate_seedream_4_size("2560x1440")  # 不抛错即通过
        _validate_seedream_4_size("2048x2048")
        with self.assertRaises(HTTPException):
            _validate_seedream_4_size("1024x1024")

    def test_seedream_fullwidth_not_bypassed(self) -> None:
        """旧实现下全角会让 `"x" not in size` 成立并直接 return，绕过校验。"""
        _validate_seedream_4_size("2560" + FULLWIDTH_MULTIPLY + "1440")
        with self.assertRaises(HTTPException):
            _validate_seedream_4_size("1024" + FULLWIDTH_MULTIPLY + "1024")

    def test_seedream_ignores_non_pixel_values(self) -> None:
        _validate_seedream_4_size("1K")  # 档位别名交给上游
        _validate_seedream_4_size(None)


class ImageDimensionProbeTest(unittest.TestCase):
    """media_service 从字节头探测真实宽高。"""

    def test_png(self) -> None:
        png = bytearray(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR")
        png += struct.pack(">II", 768, 1024) + b"\x08\x06\x00\x00\x00" + b"\x00" * 8
        self.assertEqual(_probe_image_dimensions(bytes(png)), (768, 1024))

    def test_gif(self) -> None:
        data = b"GIF89a" + struct.pack("<HH", 100, 200) + b"\x00" * 20
        self.assertEqual(_probe_image_dimensions(data), (100, 200))

    def test_bmp(self) -> None:
        bmp = bytearray(b"BM" + b"\x00" * 24)
        struct.pack_into("<ii", bmp, 18, 320, 240)
        self.assertEqual(_probe_image_dimensions(bytes(bmp)), (320, 240))

    def test_jpeg_minimal_sof0(self) -> None:
        jpeg = (
            b"\xff\xd8"
            + b"\xff\xc0"
            + (11).to_bytes(2, "big")
            + bytes([8])
            + struct.pack(">HH", 1536, 2048)
            + bytes([1, 1, 0x11, 0x00])
            + b"\x00" * 8
        )
        self.assertEqual(_probe_image_dimensions(jpeg), (2048, 1536))

    def test_webp_vp8x(self) -> None:
        webp = bytearray(b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8X" + b"\x00" * 14)
        webp[24:27] = (768 - 1).to_bytes(3, "little")
        webp[27:30] = (1024 - 1).to_bytes(3, "little")
        self.assertEqual(_probe_image_dimensions(bytes(webp)), (768, 1024))

    def test_unsupported_or_broken_returns_none(self) -> None:
        """探测是尽力而为，不能因为识别不了就抛错。"""
        for data in (b"", b"\x89PNG", b"plain text not an image" * 2, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40):
            with self.subTest(data=data[:12]):
                self.assertIsNone(_probe_image_dimensions(data))


class RequestedImageSizeTest(unittest.TestCase):
    """从落库的 params_payload 里取出请求尺寸，用于比对告警。"""

    def test_ascii_and_fullwidth_both_recognised(self) -> None:
        self.assertEqual(_requested_image_size('{"watermark": false, "size": "864x1152"}'), (864, 1152))
        self.assertEqual(_requested_image_size('{"size": "864\xd71152"}'), (864, 1152))

    def test_missing_or_invalid(self) -> None:
        for payload in ('{"watermark": false}', '{"size": 1024}', "{not json", None, '{"size": "3:4"}'):
            with self.subTest(payload=payload):
                self.assertIsNone(_requested_image_size(payload))


if __name__ == "__main__":
    unittest.main()
