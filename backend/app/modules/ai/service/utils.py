"""AI 服务层共享工具。"""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Iterable
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import select

from app.core.config import settings
from app.modules.ai.model.ai import AiModel, AiResponseFormatRequest

logger = logging.getLogger(__name__)


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
    now = datetime.now(UTC)
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


def _safe_rate(value: Any, label: str) -> float:
    """定价数值容错：非法配置（如 "0.15元"）按 0 计费并告警，绝不因定价脏数据打断调用收尾。"""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        logger.warning("AI 模型定价配置非法 %s=%r，按 0 计费（请检查 pricing_config）", label, value)
        return 0.0


def _calculate_cost_micro_usd(model: AiModel, usage: dict[str, Any]) -> int:
    pricing = _loads(model.pricing_config)
    if not isinstance(pricing, dict):
        return 0
    input_rate = _safe_rate(pricing.get("input_per_1m") or pricing.get("inputPer1m"), "input_per_1m")
    output_rate = _safe_rate(pricing.get("output_per_1m") or pricing.get("outputPer1m"), "output_per_1m")
    prompt_tokens = int(usage.get("promptTokens") or 0)
    completion_tokens = int(usage.get("completionTokens") or 0)
    usd = (prompt_tokens / 1_000_000 * input_rate) + (completion_tokens / 1_000_000 * output_rate)
    return int(round(usd * 1_000_000))


# 请求级 options 的保留字：这些键是适配器按服务端参数构造的 payload 主字段
# （OpenAI 系 model/messages/input、Claude system、Gemini contents、rerank query/documents、
# 流式开关 stream），允许请求 options 覆盖会打穿注入检测、模型白名单与审计可信度（AI-002）。
_OPTIONS_RESERVED_KEYS = frozenset(
    {"model", "messages", "input", "prompt", "contents", "query", "documents", "stream", "system"}
)


def _options_without_governance(options: dict[str, Any]) -> dict[str, Any]:
    data = dict(options or {})
    data.pop("timeout", None)
    # 静默丢弃会让调用方误以为生效（如以为能覆盖 system 提示词）→ 只记键名（值可能含
    # 提示词等敏感内容），便于定位；不抛错以免直接打断历史调用方（P2）
    dropped = sorted(key for key in data if key in _OPTIONS_RESERVED_KEYS or key.startswith("_"))
    if dropped:
        logger.warning("请求 options 含保留键，已被丢弃", extra={"dropped_option_keys": dropped})
    return {k: v for k, v in data.items() if k not in _OPTIONS_RESERVED_KEYS and not k.startswith("_")}


def make_absolute_url(path: str) -> str:
    """相对路径 → 绝对 URL（生图参考图等场景；原 runtime_service 定义，AI-013 搬迁归位）。"""
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
        return path
    if path.startswith("/"):
        base_url = settings.BACKEND_URL or settings.EXTERNAL_URL
        if not base_url:
            host = settings.HOST
            if host == "0.0.0.0":
                host = "127.0.0.1"
            base_url = f"http://{host}:{settings.PORT}"

        return f"{base_url.rstrip('/')}{path}"
    return path


def collect_ids(items: list[dict], camel: str, snake: str) -> set:
    """从一批 dict 中收集关联 id（兼容 camelCase / snake_case 两种 key）。"""
    ids: set = set()
    for d in items:
        value = d.get(camel)
        if value is None:
            value = d.get(snake)
        if value is not None:
            ids.add(value)
    return ids


def bulk_attr_map(session, model: Any, ids: set, attr: str) -> dict:
    """一次性按 id 批量加载关联实体的某个属性，返回 id→属性值 映射（列表装饰防 N+1）。"""
    if not ids:
        return {}
    rows = session.exec(select(model).where(model.id.in_(ids))).all()
    return {row.id: getattr(row, attr) for row in rows}


def statement_including_deleted(statement):
    """AI-034 逃生口：本语句跳过 Session 级软删过滤。

    适用两类场景：唯一性校验（软删行仍占用 code 唯一键，新建重用同 code 会撞库层约束）
    与软删恢复（sync_models / import_catalog 读出软删行复活）。
    """
    from app.core.database import INCLUDE_DELETED_EXECUTION_OPTION

    return statement.execution_options(**{INCLUDE_DELETED_EXECUTION_OPTION: True})


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
    """产出「本次调用专用」的适配器副本，按调用方超时收紧上游。

    语义是 httpx 的 read timeout（两次数据到达之间的最大间隔），并非整条流的总时长上限：
    流式场景下它约束逐 chunk 的静默间隔，防上游挂死；对下游客户端的连接保活由
    _with_heartbeat 负责，两者正交，勿混用。

    必须是副本而非原地改 adapter：适配器实例由 ``factory.build_adapter`` 池化跨请求复用
    （AI-017），原地改 timeout/client 再 finally 还原会在并发请求间互相覆盖——A 归还的
    旧值可能把 B 正在使用的超时改小，且流式路径的 with 块在生成器真正读上游之前就退出，
    还原后 profile.timeout 事实上从未生效。
    副本用浅拷贝：api_key/base_url/extra_config 等均为初始化期只读字段，共享安全；
    ``with_options`` 不新建底层 httpx 连接池（共享 transport），故副本无需 close。
    """
    if timeout is None:
        yield adapter
        return
    call_adapter = copy.copy(adapter)
    call_adapter.timeout = float(timeout)
    client = getattr(adapter, "client", None)
    if client is not None and hasattr(client, "with_options"):
        call_adapter.client = client.with_options(timeout=float(timeout))
    yield call_adapter


@asynccontextmanager
async def _adapter_timeout_async(adapter, timeout: int | None):
    """_adapter_timeout 的异步通道版本（异步审查 P0-4）：副本纪律与 docstring 语义
    完全一致（read timeout = 逐 chunk 静默间隔，非整条流时长上限）。openai SDK 的
    异步客户端按调用临时创建并在构造期带超时（stream_chat_async），不经过 with_options
    分支——异步客户端不驻留池化实例，无需副本共享顾虑。"""
    if timeout is None:
        yield adapter
        return
    call_adapter = copy.copy(adapter)
    call_adapter.timeout = float(timeout)
    yield call_adapter
