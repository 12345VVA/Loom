"""
轻量级请求指标。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings

_lock = threading.Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_errors: dict[tuple[str, str, str], int] = defaultdict(int)  # (method, path, "4xx"/"5xx")
_latency_total: dict[tuple[str, str], float] = defaultdict(float)
_latency_count: dict[tuple[str, str], int] = defaultdict(int)
_events: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录最小请求量和延迟统计，供 /metrics 输出。"""

    async def dispatch(self, request: Request, call_next):
        if not settings.METRICS_ENABLED:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        method = request.method
        with _lock:
            _requests[(method, path, response.status_code)] += 1
            if response.status_code >= 400:
                # 错误维度（按状态族聚合，供错误率告警）。已知边界：SSE 流内失败
                # 的响应状态恒为 200（异常发生在流体阶段），此维度测不到——流内
                # 失败由 ExceptionGuard 的规范化日志与 agent/workflow 终态事件覆盖
                status_class = "5xx" if response.status_code >= 500 else "4xx"
                _errors[(method, path, status_class)] += 1
            _latency_total[(method, path)] += elapsed
            _latency_count[(method, path)] += 1
        return response


def record_metric_event(name: str, **labels: str | int | None) -> None:
    normalized = tuple(sorted((key, str(value)) for key, value in labels.items() if value is not None))
    with _lock:
        _events[(name, normalized)] += 1


def render_metrics() -> str:
    lines = [
        "# HELP loom_http_requests_total Total HTTP requests.",
        "# TYPE loom_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status_code), value in sorted(_requests.items()):
            lines.append(f'loom_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {value}')
        lines.extend(
            [
                "# HELP loom_http_errors_total HTTP error responses by status class.",
                "# TYPE loom_http_errors_total counter",
            ]
        )
        for (method, path, status_class), value in sorted(_errors.items()):
            lines.append(f'loom_http_errors_total{{method="{method}",path="{path}",class="{status_class}"}} {value}')
        lines.extend(
            [
                "# HELP loom_http_request_duration_seconds_avg Average HTTP request duration.",
                "# TYPE loom_http_request_duration_seconds_avg gauge",
            ]
        )
        for key, total in sorted(_latency_total.items()):
            count = _latency_count.get(key, 0)
            if not count:
                continue
            method, path = key
            lines.append(
                f'loom_http_request_duration_seconds_avg{{method="{method}",path="{path}"}} {total / count:.6f}'
            )
        lines.extend(
            [
                "# HELP loom_events_total Framework event counters.",
                "# TYPE loom_events_total counter",
            ]
        )
        for (name, labels), value in sorted(_events.items()):
            label_items = [f'event="{name}"', *(f'{key}="{val}"' for key, val in labels)]
            lines.append(f"loom_events_total{{{','.join(label_items)}}} {value}")
    return "\n".join(lines) + "\n"
