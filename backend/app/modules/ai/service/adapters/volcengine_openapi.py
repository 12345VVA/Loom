"""火山引擎 OpenAPI（volcengineapi.com）访问工具。

推理域名 ark.cn-beijing.volces.com 走 Bearer API Key；模型开通状态等管理接口走
火山 OpenAPI，仅支持 Access Key（AK/SK）+ 火山 V4 签名（HMAC-SHA256，仿 AWS
SigV4 但前缀为 "HMAC-SHA256"）。本模块自实现签名，避免引入官方 volcengine SDK
重依赖。

当前仅覆盖 ListModelActivations（拉取账号已开通的基础模型）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

ARK_OPENAPI_HOST = "ark.cn-beijing.volcengineapi.com"
ARK_OPENAPI_REGION = "cn-beijing"
ARK_OPENAPI_SERVICE = "ark"
LIST_MODEL_ACTIVATIONS_VERSION = "2024-01-01"
# 分页防御上限：火山在售模型数百个，100/页足够，封顶防异常响应导致死循环
_MAX_PAGES = 50


def sign_volcengine_v4(
    *,
    method: str,
    host: str,
    path: str,
    query: dict[str, str],
    body: str,
    access_key: str,
    secret_key: str,
    region: str = ARK_OPENAPI_REGION,
    service: str = ARK_OPENAPI_SERVICE,
    now: datetime | None = None,
) -> dict[str, str]:
    """生成火山 V4 签名请求头（Content-Type/Host/X-Content-Sha256/X-Date/Authorization）。"""
    now = now or datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_scope = now.strftime("%Y%m%d")
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    def _uri_encode(value: str) -> str:
        # RFC3986：unreserved 字符（-_.~ 字母数字）不编码
        return urllib.parse.quote(value, safe="-_.~")

    canonical_query = "&".join(
        f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(query.items())
    )
    signed_header_names = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        f"content-type:application/json\nhost:{host.lower()}\n"
        f"x-content-sha256:{body_hash}\nx-date:{x_date}\n"
    )
    canonical_request = "\n".join([method.upper(), path or "/", canonical_query, canonical_headers, signed_header_names, body_hash])

    credential_scope = f"{date_scope}/{region}/{service}/request"
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()]
    )

    def _hmac(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    k_signing = _hmac(_hmac(_hmac(_hmac(secret_key.encode("utf-8"), date_scope), region), service), "request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "Host": host.lower(),
        "X-Date": x_date,
        "X-Content-Sha256": body_hash,
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_header_names}, Signature={signature}"
        ),
    }


def list_model_activations(
    *,
    access_key: str,
    secret_key: str,
    page_number: int = 1,
    page_size: int = 100,
    with_price: bool = True,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """调用 ListModelActivations，返回单页原始响应（Items/PageNumber/TotalCount 等）。"""
    body = json.dumps(
        {
            "Filter": {"States": ["Available"], "IncludeDeprecatedModels": False},
            "PageNumber": page_number,
            "PageSize": page_size,
            "WithPrice": with_price,
        },
        separators=(",", ":"),
    )
    headers = sign_volcengine_v4(
        method="POST",
        host=ARK_OPENAPI_HOST,
        path="/",
        query={"Action": "ListModelActivations", "Version": LIST_MODEL_ACTIVATIONS_VERSION},
        body=body,
        access_key=access_key,
        secret_key=secret_key,
    )
    response = httpx.post(
        f"https://{ARK_OPENAPI_HOST}/",
        params={"Action": "ListModelActivations", "Version": LIST_MODEL_ACTIVATIONS_VERSION},
        content=body,
        headers=headers,
        timeout=timeout,
    )
    if response.status_code != 200:
        message = _extract_openapi_error(response)
        raise RuntimeError(f"火山方舟 ListModelActivations 失败: {response.status_code} {message}")
    data = response.json()
    # 火山 OpenAPI 业务错误同样是 HTTP 200 + ResponseMetaData.Error
    error = ((data.get("ResponseMetaData") or {}).get("Error")) if isinstance(data, dict) else None
    if error:
        raise RuntimeError(
            f"火山方舟 ListModelActivations 失败: {error.get('Code')} {error.get('Message')}"
        )
    return data


def iter_ark_available_models(
    *,
    access_key: str,
    secret_key: str,
    timeout: float = 30.0,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """分页拉取全部已开通模型，映射为模型同步统一结构。

    返回字段：code（FoundationModelName）、name（DisplayName）、state、pricing（原始
    计费信息 dict，供 sync 落 pricing_config）、deprecated。
    """
    items: list[dict[str, Any]] = []
    page_number = 1
    total_count: int | None = None
    while page_number <= _MAX_PAGES:
        data = list_model_activations(
            access_key=access_key,
            secret_key=secret_key,
            page_number=page_number,
            page_size=page_size,
            with_price=True,
            timeout=timeout,
        )
        page_items = data.get("Items") or []
        items.extend(item for item in page_items if isinstance(item, dict))
        total_count = int(data.get("TotalCount") or 0)
        if not page_items or len(items) >= total_count:
            break
        page_number += 1
    return [_map_ark_model(item) for item in items]


def _map_ark_model(item: dict[str, Any]) -> dict[str, Any]:
    pricing = {
        key: item[key]
        for key in ("ChargeItems", "MultiChargeItems", "InitialInferenceFreeUsage", "FreeResourcePackItems")
        if item.get(key)
    }
    return {
        "code": str(item.get("FoundationModelName") or "").strip(),
        "name": str(item.get("DisplayName") or item.get("FoundationModelName") or "").strip(),
        "state": item.get("State"),
        "vendor": item.get("VendorName"),
        "deprecated": bool(item.get("IsDeprecated")),
        "limited_activation": bool(item.get("IsLimitedActivation")),
        "pricing": pricing or None,
    }


def _extract_openapi_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text[:300]
    error = (data.get("ResponseMetaData") or {}).get("Error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return f"{error.get('Code')} {error.get('Message')}"[:300]
    return str(data)[:300]
