"""
轻量级请求指标。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_errors: dict[tuple[str, str, str], int] = defaultdict(int)  # (method, path, "4xx"/"5xx")
_latency_total: dict[tuple[str, str], float] = defaultdict(float)
_latency_count: dict[tuple[str, str], int] = defaultdict(int)
_events: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
# SSE 活跃连接数（按端点），set_gauge 的结构化上游
_sse_active: dict[str, int] = defaultdict(int)

# P2-8（异步审查）：指标序列上限。path 已按路由模板归一，但 404 探测等未匹配请求
# 仍可能产生长尾序列；超出上限的写入并入聚合计数器丢弃，防内存无界增长。
# 1000 条/字典对全部内置维度（route 模板数有限）远够用，触发即说明有新泄漏源
_MAX_SERIES_PER_DICT = 1000
_series_overflow_total = 0
_overflow_warned = False


def _normalize_path(scope: Scope) -> str:
    """原始 path → 路由模板（异步审查 P2-8 高基数根治）。

    FastAPI/Starlette 在路由完成后把匹配到的 route 写入 scope["route"]，本中间件
    在响应期（send 捕获时）读取已是路由后——取 ``route.path`` 模板即可让
    /uploads/<date>/<uuid> 这类每资源一 path 的端点收敛为单条序列。未匹配路由
    （404 探测等）回退原 path 并截断，兜住长尾。"""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    return (scope.get("path") or "")[:120]


def _bump_counter(series: dict, key) -> None:
    """带序列上限的计数写入：新序列超上限并入聚合计数器丢弃（调用方须持 _lock）。"""
    global _series_overflow_total, _overflow_warned
    if key in series:
        series[key] += 1
        return
    if len(series) >= _MAX_SERIES_PER_DICT:
        _series_overflow_total += 1
        if not _overflow_warned:
            _overflow_warned = True
            logger.warning(
                "指标序列达上限 %d，后续新序列并入 loom_metric_series_overflow_total 丢弃"
                "（应排查新的高基数 label 来源）",
                _MAX_SERIES_PER_DICT,
            )
        return
    series[key] = 1


def set_gauge(name: str, value: float, **labels: str | int | None) -> None:
    """设置运行时 gauge（DB 池水位 / anyio 线程池 / SSE 连接数 / 队列积压 / loop 滞后）。

    gauge 由调用方定义，数量有界，不做序列上限。labels 顺序规范化（同 record_metric_event）。"""
    normalized = tuple(sorted((key, str(value_)) for key, value_ in labels.items() if value_ is not None))
    with _lock:
        _gauges[(name, normalized)] = value


def sse_connection_opened(endpoint: str) -> None:
    """SSE 连接建立计数（流式生成器入口调用）。"""
    with _lock:
        _sse_active[endpoint] += 1
        _gauges[("sse_connections_active", (("endpoint", endpoint),))] = float(_sse_active[endpoint])


def sse_connection_closed(endpoint: str) -> None:
    """SSE 连接关闭计数（流式生成器 finally 调用，与 opened 严格配对）。"""
    with _lock:
        _sse_active[endpoint] = max(0, _sse_active[endpoint] - 1)
        _gauges[("sse_connections_active", (("endpoint", endpoint),))] = float(_sse_active[endpoint])


class MetricsMiddleware:
    """记录最小请求量和延迟统计，供 /metrics 输出。

    纯 ASGI（异步审查 P1-1，样板 operation_log/body_buffer/exception_guard）。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.METRICS_ENABLED:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        holder = {"status": 0, "elapsed": 0.0}

        async def send_capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                holder["status"] = message.get("status", 0)
                # 计时口径与原 BaseHTTPMiddleware 版对齐：到 response.start 为止，
                # 不含流式 body 的传输时长
                holder["elapsed"] = time.perf_counter() - started
            await send(message)

        await self.app(scope, receive, send_capture)

        path = _normalize_path(scope)
        method = scope.get("method", "")
        status_code = holder["status"]
        elapsed = holder["elapsed"] or (time.perf_counter() - started)
        with _lock:
            _bump_counter(_requests, (method, path, status_code))
            if status_code >= 400:
                # 错误维度（按状态族聚合，供错误率告警）。已知边界：SSE 流内失败
                # 的响应状态恒为 200（异常发生在流体阶段），此维度测不到——流内
                # 失败由 ExceptionGuard 的规范化日志与 agent/workflow 终态事件覆盖
                status_class = "5xx" if status_code >= 500 else "4xx"
                _bump_counter(_errors, (method, path, status_class))
            latency_key = (method, path)
            if latency_key in _latency_count or len(_latency_count) < _MAX_SERIES_PER_DICT:
                _latency_total[latency_key] += elapsed
                _latency_count[latency_key] += 1


def record_metric_event(name: str, **labels: str | int | None) -> None:
    normalized = tuple(sorted((key, str(value)) for key, value in labels.items() if value is not None))
    with _lock:
        _bump_counter(_events, (name, normalized))


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
                "# TYPE loom_metric_series_overflow_total counter",
                f"loom_metric_series_overflow_total {_series_overflow_total}",
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
        # 运行时 gauge：按指标名分组输出（loom_db_pool_checkedout / loom_thread_pool_borrowed /
        # loom_sse_connections_active{endpoint} / loom_celery_queue_depth{queue} / loom_event_loop_lag_seconds ...）
        by_name: dict[str, list[tuple[tuple[tuple[str, str], ...], float]]] = defaultdict(list)
        for (name, labels), value in sorted(_gauges.items()):
            by_name[name].append((labels, value))
        for name, items in sorted(by_name.items()):
            lines.append(f"# HELP loom_{name} Runtime gauge (async review observability).")
            lines.append(f"# TYPE loom_{name} gauge")
            for labels, value in sorted(items):
                if labels:
                    label_items = [f'{key}="{val}"' for key, val in labels]
                    lines.append(f"loom_{name}{{{','.join(label_items)}}} {value}")
                else:
                    lines.append(f"loom_{name} {value}")
    return "\n".join(lines) + "\n"
