"""
最小 i18n 消息解析。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=16)
def _load_locale(locale: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def t(key: str, locale: str = "zh-CN", **params) -> str:
    template = _load_locale(locale).get(key) or _load_locale("zh-CN").get(key) or key
    try:
        return template.format(**params)
    except Exception:
        return template
