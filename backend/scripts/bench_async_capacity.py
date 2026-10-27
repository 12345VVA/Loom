"""异步容量压测驱动（异步审查第二轮·批 D，压测方案文档的执行器）。

四曲线中的可自动化的三条（agent 曲线依赖模型上游，未纳入）：
  crud   并发打管理端列表接口（curve 1）
  sse    并发建立 workflow /stream 长连接读心跳（curve 2；P0-2 核心验证：
         pool.checkedout 不应随连接数线性增长）
  mixed  SSE×30 + CRUD×并发数（curve 4 混合形态）

用法（backend/ 下）：
  venv/Scripts/python.exe scripts/bench_async_capacity.py \
      --base http://127.0.0.1:8001 --curve crud --concurrency 50 --duration 120 \
      [--instance-id 1] [--json out.json]

前置：目标实例 METRICS_ENABLED=true、RATE_LIMIT_ENABLED=false（压容量而非限流）、
  库中存在 workflow definition/instance（SSE 用）；账号 admin/123456 或经
  ADMIN_USER/ADMIN_PASS 注入。压测期间每 10s 抓一次 /metrics 关键 gauge 快照。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator

import httpx

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])  # backend/ 根，便于 import app

from app.core.config import settings  # noqa: E402

CRUD_PATH = "/admin/dict/type/page"
SSE_PATH = "/admin/workflow/instance/stream"
METRICS_KEYS = (
    "loom_db_pool_checkedout",
    "loom_thread_pool_borrowed",
    "loom_thread_pool_tasks_waiting",
    "loom_sse_connections_active",
    "loom_celery_unacked_total",
    "loom_event_loop_lag_seconds",
)


def _build_slider_verify(target_x: float) -> str:
    """构造合规滑块轨迹：单调递增、时长 800ms、8 点（含时间轴 t，末点 t=duration）。

    对齐 auth_captcha 的 H1 时间轴交叉校验：t 非负单调、末点 t ≤ duration+200、
    duration - 末点 t ≤ MAX_RELEASE_GAP_MS(5000)。"""
    import json

    track = [
        {"x": round(target_x * i / 7, 2), "t": round(800 * i / 7)}
        for i in range(8)
    ]
    track[-1]["x"] = target_x
    track[-1]["t"] = 800
    return json.dumps({"x": target_x, "duration": 800, "track": track})


async def login(client: httpx.AsyncClient, base: str, username: str, password: str) -> str:
    """滑块验证码登录：答案从 Redis 侧读取（基础设施凭据的部署验证，非渗透）。

    Redis 值为验证码服务专用 seal 密文（HMAC+Fernet），复用其 _unseal_challenge
    解封取 target_x；challenge 绑定签发 IP，脚本与验证码同源（127.0.0.1）故成立。"""
    import redis as redis_lib

    from app.modules.base.service.auth_captcha import _unseal_challenge

    captcha = (await client.get("/admin/base/open/captcha?width=280&height=160")).json()["data"]
    captcha_id = captcha["captchaId"]
    r = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    payload = _unseal_challenge(r.get(f"verify:slider:{captcha_id}")) or {}
    target_x = float(payload["target_x"])
    resp = await client.post(
        "/admin/base/open/login",
        json={
            "username": username,
            "password": password,
            "captchaId": captcha_id,
            "verifyCode": _build_slider_verify(target_x),
        },
        headers={"Origin": base},
    )
    data = resp.json().get("data") or {}
    token = data.get("token") or data.get("access_token")
    if not token:
        raise SystemExit(f"登录失败（检查账号口令）: {resp.text[:300]}")
    return token


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * p / 100))
    return ordered[index]


def _summary(latencies: list[float], errors: int, wall: float) -> dict:
    return {
        "requests": len(latencies) + errors,
        "errors": errors,
        "rps": round((len(latencies) + errors) / wall, 1) if wall else 0.0,
        "p50_ms": round(_percentile(latencies, 50) * 1000, 1),
        "p95_ms": round(_percentile(latencies, 95) * 1000, 1),
        "p99_ms": round(_percentile(latencies, 99) * 1000, 1),
        "max_ms": round(max(latencies) * 1000, 1) if latencies else 0.0,
    }


async def crud_worker(client: httpx.AsyncClient, headers: dict, deadline: float, latencies: list[float], errors: list) -> None:
    while time.monotonic() < deadline:
        start = time.perf_counter()
        try:
            resp = await client.get(CRUD_PATH, params={"page": 1, "size": 20}, headers=headers)
            if resp.status_code != 200:
                errors.append(f"HTTP {resp.status_code}")
            else:
                latencies.append(time.perf_counter() - start)
        except Exception as exc:  # noqa: BLE001 - 压测驱动对任意网络错误计数继续
            errors.append(str(exc)[:80])


async def sse_worker(
    client: httpx.AsyncClient, headers: dict, instance_id: int, deadline: float, latencies: list[float], errors: list
) -> None:
    """建流后读帧至 deadline；连接建立耗时计入 latencies，心跳计数用于判定流活性。"""
    while time.monotonic() < deadline:
        start = time.perf_counter()
        try:
            async with client.stream("GET", SSE_PATH, params={"instanceId": instance_id}, headers=headers) as resp:
                if resp.status_code != 200:
                    errors.append(f"HTTP {resp.status_code}")
                    await asyncio.sleep(1)
                    continue
                latencies.append(time.perf_counter() - start)
                async for _line in _iter_lines_until(resp, deadline):
                    pass
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc)[:80])
            await asyncio.sleep(1)


async def _iter_lines_until(resp: httpx.Response, deadline: float) -> AsyncIterator[str]:
    it = resp.aiter_lines()
    while time.monotonic() < deadline:
        try:
            line = await asyncio.wait_for(anext(it), timeout=2)
        except TimeoutError:
            return
        except StopAsyncIteration:
            return
        yield line


async def metrics_sampler(client: httpx.AsyncClient, deadline: float, snapshots: list[dict]) -> None:
    """每 10s 抓 /metrics 关键 gauge（含 sse 按端点拆分），存快照。"""
    while time.monotonic() < deadline:
        try:
            resp = await client.get("/metrics")
            body = resp.text
            snapshot: dict[str, float | dict[str, float]] = {}
            for line in body.splitlines():
                if not line.startswith("loom_"):
                    continue
                name, _, value = line.rpartition(" ")
                try:
                    value_f = float(value)
                except ValueError:
                    continue
                for key in METRICS_KEYS:
                    if name.startswith(key):
                        if "{" in name:  # 带 labels（如 sse{endpoint=...}）拆字典
                            bucket = snapshot.setdefault(key, {})
                            assert isinstance(bucket, dict)
                            bucket[name] = value_f
                        else:
                            snapshot[key] = value_f
            snapshot["ts"] = time.strftime("%H:%M:%S")
            snapshots.append(snapshot)
        except Exception:  # noqa: BLE001 - 采样失败不中断压测
            pass
        await asyncio.sleep(10)


async def run(args: argparse.Namespace) -> None:
    base = args.base.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(10.0, read=60.0)) as client:
        token = await login(client, base, args.user, args.password)
        print(f"OK   login → token 已签发（{base}）")
        headers = {"Authorization": f"Bearer {token}"}

        deadline = time.monotonic() + args.duration
        latencies: list[float] = []
        errors: list = []
        snapshots: list[dict] = []

        tasks = [asyncio.create_task(metrics_sampler(client, deadline, snapshots))]
        if args.curve in ("crud", "mixed"):
            tasks += [
                asyncio.create_task(crud_worker(client, headers, deadline, latencies, errors))
                for _ in range(args.concurrency if args.curve == "crud" else 50)
            ]
        if args.curve in ("sse", "mixed"):
            sse_count = args.concurrency if args.curve == "sse" else 30
            tasks += [
                asyncio.create_task(
                    sse_worker(client, headers, args.instance_id, deadline, latencies, errors)
                )
                for _ in range(sse_count)
            ]

        await asyncio.gather(*tasks)
        wall = args.duration

        print(f"\n=== {args.curve} 并发={args.concurrency} 时长={args.duration}s @ {base} ===")
        print(json.dumps(_summary(latencies, len(errors), wall), ensure_ascii=False))
        if errors:
            from collections import Counter

            for message, count in Counter(errors).most_common(5):
                print(f"  err×{count}: {message}")
        if snapshots:
            print("\n--- /metrics 快照（每 10s）---")
            for snapshot in snapshots:
                print(json.dumps(snapshot, ensure_ascii=False))
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"summary": _summary(latencies, len(errors), wall), "snapshots": snapshots}, f, ensure_ascii=False, indent=2)
            print(f"\n快照已写 {args.json}")


def main() -> None:
    parser = argparse.ArgumentParser(description="异步容量压测驱动（CRUD/SSE/混合）")
    parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--curve", choices=("crud", "sse", "mixed"), default="crud")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--duration", type=int, default=120, help="秒")
    parser.add_argument("--instance-id", type=int, default=1, help="SSE 订阅的实例 id")
    parser.add_argument("--user", default=os_env("ADMIN_USER", settings.DEFAULT_ADMIN_USERNAME))
    parser.add_argument("--password", default=os_env("ADMIN_PASS", settings.DEFAULT_ADMIN_PASSWORD))
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


def os_env(key: str, default: str) -> str:
    import os

    return os.environ.get(key, default)


if __name__ == "__main__":
    main()
