"""Celery worker 进程的事件循环执行器治理（异步审查 P0-5 修正）。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


def run_with_sized_executor(coro: Coroutine[Any, Any, T]) -> T:
    """在新建事件循环上执行协程，并为其挂显式默认执行器。

    背景：worker 内的节点/评测代码用 stdlib ``asyncio.to_thread`` 卸载阻塞调用——
    它走 loop 默认 ThreadPoolExecutor（上限 ≈ min(32, CPU+4)），**并不经过 anyio
    limiter**（worker_process_init 设置的是 anyio 侧，对这条路径不生效）。本助手
    把 ``WORKER_THREAD_POOL_SIZE`` 显式挂为 loop 默认执行器上限，才真正约束
    worker 内 to_thread 的并发（负载测试排障时确认的机制偏差）。asyncio.run
    收尾时自动 shutdown 默认执行器。"""
    from app.core.config import settings

    async def _runner() -> T:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(
            ThreadPoolExecutor(
                max_workers=max(1, settings.WORKER_THREAD_POOL_SIZE), thread_name_prefix="worker-to-thread"
            )
        )
        return await coro

    return asyncio.run(_runner())
