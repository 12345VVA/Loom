"""百炼 OpenAPI（maas.aliyuncs.com）业务空间模型权限查询。

与推理的 compatible-mode 域名不同，模型权限接口按业务空间分子域：
``https://{WorkspaceId}.{region}.maas.aliyuncs.com/api/v1/models/permissions``，
鉴权复用 DashScope API Key（Bearer）。workspace_id 取自厂商扩展配置。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.service.adapters.base import UpstreamApiError

# 分页防御上限：200/页 * 20 页 = 4000，防止异常响应导致死循环
_MAX_PAGES = 20
_PAGE_SIZE = 200
_DEFAULT_REGION = "cn-beijing"


def list_workspace_authorized_models(
    *,
    api_key: str,
    workspace_id: str,
    region: str = _DEFAULT_REGION,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """分页拉取业务空间已授权可推理的模型，映射为模型同步统一结构。

    返回字段：code（model_id）、name（展示名）。该接口无价格与模型类型信息，
    model_type 维持 sync 的待人工分类语义。
    """
    host = f"{workspace_id}.{region}.maas.aliyuncs.com"
    url = f"https://{host}/api/v1/models/permissions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    items: list[dict[str, Any]] = []
    fetched = 0
    page_no = 1
    while page_no <= _MAX_PAGES:
        response = httpx.get(
            url,
            params={
                "authorization_scope": "AUTHORIZED",
                "action": "INFERENCE",
                "page_no": page_no,
                "page_size": _PAGE_SIZE,
            },
            headers=headers,
            timeout=timeout,
        )
        if response.status_code != 200:
            raise UpstreamApiError(
                f"百炼模型权限查询失败: {response.status_code} {_extract_error(response)}",
                request_id=_request_id(response),
            )
        data = response.json()
        if not data.get("success") or data.get("code"):
            raise UpstreamApiError(
                f"百炼模型权限查询失败: {data.get('code')} {data.get('message')}",
                request_id=data.get("request_id"),
            )
        output = data.get("output") or {}
        page_items = [item for item in (output.get("permissions") or []) if isinstance(item, dict)]
        # 服务端按 action=INFERENCE 过滤，此处对 permissions.inference 再做一层保守过滤
        items.extend(item for item in page_items if (item.get("permissions") or {}).get("inference", True))
        fetched += len(page_items)
        total = int(output.get("total") or 0)
        # 终止按服务端返回数判断：客户端过滤后数量少于 total 会误判未拉全
        if not page_items or fetched >= total:
            break
        page_no += 1

    return [
        {
            "code": str(item.get("model") or "").strip(),
            "name": str(item.get("name") or item.get("model") or "").strip(),
        }
        for item in items
        if item.get("model")
    ]


def _extract_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text[:300]
    return f"{data.get('code')} {data.get('message')}".strip()[:300] or str(data)[:300]


def _request_id(response: httpx.Response) -> str | None:
    try:
        return response.json().get("request_id")
    except Exception:
        return response.headers.get("x-request-id")
