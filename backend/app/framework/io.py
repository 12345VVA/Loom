"""
通用导入导出辅助。
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ImportExportField:
    name: str
    title: str | None = None
    required: bool = False


@dataclass(frozen=True)
class ImportExportSchema:
    fields: list[ImportExportField]
    allow_extra: bool = False

    @property
    def field_names(self) -> list[str]:
        return [item.name for item in self.fields]

    @property
    def required_names(self) -> set[str]:
        return {item.name for item in self.fields if item.required}


@dataclass
class ImportErrorItem:
    row: int
    field: str
    message: str


@dataclass
class ImportResult:
    rows: list[dict[str, str]] = field(default_factory=list)
    errors: list[ImportErrorItem] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


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


def export_rows_to_csv(rows: Iterable[dict], schema: ImportExportSchema) -> str:
    return export_dicts_to_csv(rows, schema.field_names)


def import_rows_from_csv(content: str, schema: ImportExportSchema) -> ImportResult:
    reader = csv.DictReader(io.StringIO(content))
    headers = set(reader.fieldnames or [])
    errors: list[ImportErrorItem] = []
    rows: list[dict[str, str]] = []

    missing_headers = schema.required_names - headers
    for field_name in sorted(missing_headers):
        errors.append(ImportErrorItem(row=0, field=field_name, message="缺少必填列"))

    if not schema.allow_extra:
        for field_name in sorted(headers - set(schema.field_names)):
            errors.append(ImportErrorItem(row=0, field=field_name, message="未声明的导入列"))

    for index, raw_row in enumerate(reader, start=2):
        row = {name: (raw_row.get(name) or "").strip() for name in schema.field_names}
        for field_name in schema.required_names:
            if not row.get(field_name):
                errors.append(ImportErrorItem(row=index, field=field_name, message="必填字段不能为空"))
        rows.append(row)

    return ImportResult(rows=rows, errors=errors)
