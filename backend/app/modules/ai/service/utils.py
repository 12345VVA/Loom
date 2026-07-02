"""AI 服务层共享工具。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.modules.ai.model.ai import AiModel, AiResponseFormatRequest


def _validate_json_config(value: str | None, field_label: str, expected_type: type | None = None) -> None:
    if value in (None, ""):
        return
    try:
        parsed = json.loads(value)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_label} 必须是合法 JSON") from exc
    if expected_type is not None and not isinstance(parsed, expected_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_label} 必须是 JSON 对象")


def _dump_response_format(value: str | None) -> str | None:
    response_format = normalize_response_format(_loads(value))
    if not response_format:
        return None
    return json.dumps(response_format, ensure_ascii=False)


def normalize_response_format(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, AiResponseFormatRequest):
        value = value.model_dump(by_alias=True, exclude_none=True)
    elif hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(value, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat 必须是 JSON 对象")

    format_type = value.get("type") or value.get("response_format") or "text"
    if format_type == "text":
        return None
    if format_type == "json_object":
        return {"type": "json_object"}
    if format_type != "json_schema":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.type 仅支持 text、json_object、json_schema"
        )

    json_schema = value.get("json_schema") or value.get("jsonSchema")
    if hasattr(json_schema, "model_dump"):
        json_schema = json_schema.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(json_schema, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema 必须是 JSON 对象"
        )

    name = str(json_schema.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema.name 不能为空")
    if len(name) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="responseFormat.jsonSchema.name 仅支持字母、数字、下划线、短横线，最长 64",
        )

    schema = json_schema.get("schema") or json_schema.get("schema_")
    if not isinstance(schema, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema.schema 必须是 JSON 对象"
        )

    normalized_schema = {
        "name": name,
        "schema": schema,
        "strict": bool(json_schema.get("strict", True)),
    }
    description = json_schema.get("description")
    if description:
        normalized_schema["description"] = str(description)
    return {"type": "json_schema", "json_schema": normalized_schema}


def _is_structured_response(response_format: dict[str, Any] | None) -> bool:
    return bool(response_format and response_format.get("type") in {"json_object", "json_schema"})


def _with_parsed_content(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, str):
        return {**result, "parsed": None, "parseError": "content 不是字符串"}
    return {**result, **_parse_content(content)}


def _parse_content(content: str) -> dict[str, Any]:
    try:
        return {"parsed": json.loads(content), "parseError": None}
    except Exception as exc:
        return {"parsed": None, "parseError": str(exc)}


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _loads(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _window_bounds(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "minute":
        start = now.replace(second=0, microsecond=0)
        return start, start + timedelta(minutes=1)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _calculate_cost_micro_usd(model: AiModel, usage: dict[str, Any]) -> int:
    pricing = _loads(model.pricing_config)
    if not isinstance(pricing, dict):
        return 0
    input_rate = float(pricing.get("input_per_1m") or pricing.get("inputPer1m") or 0)
    output_rate = float(pricing.get("output_per_1m") or pricing.get("outputPer1m") or 0)
    prompt_tokens = int(usage.get("promptTokens") or 0)
    completion_tokens = int(usage.get("completionTokens") or 0)
    usd = (prompt_tokens / 1_000_000 * input_rate) + (completion_tokens / 1_000_000 * output_rate)
    return int(round(usd * 1_000_000))


def _options_without_governance(options: dict[str, Any]) -> dict[str, Any]:
    data = dict(options or {})
    data.pop("timeout", None)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def summarize_prompt(value: Any, limit: int = 240) -> dict[str, Any]:
    text = str(value or "")
    return {
        "length": len(text),
        "preview": text[:limit],
        "truncated": len(text) > limit,
    }


def sanitize_options_for_log(options: dict[str, Any] | None) -> dict[str, Any]:
    def _sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                lowered = str(key).lower()
                if lowered in {"api_key", "apikey", "authorization"}:
                    result[key] = "***"
                    continue
                if lowered in {"b64_json", "b64json", "base64", "image", "image_data"}:
                    result[key] = _summarize_binary_like(item)
                    continue
                result[key] = _sanitize(item)
            return result
        if isinstance(value, list):
            return [_sanitize(item) for item in value[:10]]
        if isinstance(value, str) and len(value) > 500:
            return {"type": "string", "length": len(value), "preview": value[:120]}
        return value

    return _sanitize(dict(options or {}))


def summarize_image_result_items(items: Iterable[Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:10]:
        if not isinstance(item, dict):
            result.append({"type": type(item).__name__})
            continue
        if item.get("url") or item.get("image_url") or item.get("imageUrl"):
            url = item.get("url") or item.get("image_url") or item.get("imageUrl")
            result.append({"kind": "url", "preview": str(url)[:160]})
            continue
        b64 = item.get("b64_json") or item.get("b64Json") or item.get("base64")
        if b64:
            result.append(_summarize_binary_like(b64, kind="b64"))
            continue
        result.append({"kind": "unknown", "keys": sorted(str(key) for key in item.keys())[:10]})
    return result


def extract_request_id(value: Any) -> str | None:
    candidates = [
        getattr(value, "_request_id", None),
        getattr(value, "request_id", None),
    ]
    response = getattr(value, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers:
            candidates.extend(
                [
                    headers.get("x-request-id"),
                    headers.get("request-id"),
                    headers.get("x-tt-logid"),
                ]
            )
    for item in candidates:
        if item:
            return str(item)
    return None


def _summarize_binary_like(value: Any, kind: str = "binary") -> dict[str, Any]:
    text = str(value or "")
    return {
        "kind": kind,
        "length": len(text),
        "is_data_url": text.startswith("data:"),
        "preview": text[:60],
    }


@contextmanager
def _adapter_timeout(adapter, timeout: int | None):
    if timeout is None:
        yield
        return
    previous_timeout = getattr(adapter, "timeout", None)
    previous_client = getattr(adapter, "client", None)
    adapter.timeout = float(timeout)
    if previous_client is not None and hasattr(previous_client, "with_options"):
        adapter.client = previous_client.with_options(timeout=float(timeout))
    try:
        yield
    finally:
        adapter.timeout = previous_timeout
        if previous_client is not None:
            adapter.client = previous_client
