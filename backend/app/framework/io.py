"""
通用导入导出辅助。
"""
from __future__ import annotations

import csv
import io
from typing import Iterable


def export_dicts_to_csv(rows: Iterable[dict], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def import_dicts_from_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return [dict(row) for row in reader]
