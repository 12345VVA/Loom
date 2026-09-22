"""生图尺寸入参的归一化与校验。

为什么单独成模块
----------------
「两个尺寸值看起来一模一样、实际不是」是个跨适配器的通用陷阱：

- 中文输入法或从文档复制会带出全角乘号 ``×`` (U+00D7)
- 数学符号区还有 ``✕`` (U+2715)、``⨯`` (U+2A2F)、``⨉`` (U+2A09)、``╳`` (U+2573)
- 西里尔 ``х`` (U+0445)、希腊 ``Χ`` (U+03A7) 与 ASCII ``x`` 肉眼几乎无法区分
- 全角数字 ``８６４`` 同样常见

历史事故：ToAPIs 适配器与百炼/火山路径都曾用 ``"x" in size`` 直接判定，
全角输入命中失败后被**静默回落**成默认尺寸（``1024x1024``），全程无日志，
问题隐藏了一整天才被发现。

凡是「人可能手填尺寸」的适配器，都应走这里的归一化，而不是自己写字符判断。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.modules.ai.service.adapters.base import UpstreamApiError

# 各类易被当作乘号输入的字符
_SIZE_SEPARATORS = ("×", "✕", "✖", "⨯", "⨉", "╳", "＊", "*", "х", "Χ", "χ")

# 像素尺寸：1~5 位数字 + ASCII x + 1~5 位数字
_PIXEL_SIZE_RE = re.compile(r"^(\d{1,5})x(\d{1,5})$")


def normalize_size_token(value: Any) -> str | None:
    """把尺寸输入归一化为 ASCII 小写形式；空值返回 None。

    归一化内容：NFKC（全角数字/全角字母 → 半角）、大小写、空白、各类乘号 → ASCII ``x``。

    >>> normalize_size_token("864×1152")
    '864x1152'
    >>> normalize_size_token("８６４ｘ１１５２")
    '864x1152'
    >>> normalize_size_token(" 3 : 4 ")
    '3:4'
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not text:
        return None
    for ch in _SIZE_SEPARATORS:
        text = text.replace(ch, "x")
    text = re.sub(r"\s+", "", text)
    return text or None


def parse_pixel_size(value: Any) -> tuple[int, int] | None:
    """解析像素尺寸（归一化后必须是 ``宽x高``）；非像素格式或非法值返回 None。"""
    normalized = normalize_size_token(value)
    if not normalized:
        return None
    matched = _PIXEL_SIZE_RE.match(normalized)
    if not matched:
        return None
    width, height = int(matched.group(1)), int(matched.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def ensure_pixel_size(value: Any, *, default: str = "1024x1024", label: str = "ToAPIs") -> str:
    """像素尺寸强校验。

    - 未提供（None/空串）→ 返回 ``default``（合法兜底，不是静默吞错）
    - 提供了且归一化后是合法像素尺寸 → 返回归一化结果
    - 提供了但非法 → 抛 :class:`UpstreamApiError`（**不再静默回落成默认尺寸**）
    """
    normalized = normalize_size_token(value)
    if normalized is None:
        return default
    if not _PIXEL_SIZE_RE.match(normalized):
        raise UpstreamApiError(
            "%s 尺寸参数非法：%r（归一化后为 %r）。像素尺寸须形如 '1024x1024'，"
            "分隔符必须是 ASCII 小写 'x'，不接受比例写法。" % (label, value, normalized)
        )
    return normalized
