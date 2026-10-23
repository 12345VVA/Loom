"""同会话 run 串行锁（设计 3.4.4，评审 P0-3）：锁所有权与安全释放。

- Redis 原子锁 ``SET agent:runlock:{session_id} NX EX``，锁值 = trace_id（唯一所有者）；
- 释放经 Lua compare-and-delete（仅锁值 = 自己 trace_id 才删除，防超时后误删他 run 的锁）；
- run 每步调度前校验所有权：锁过期或被他人持有 → 立即停止调度（外层置 cancelled）；
- 不做续期（TTL = timeout_seconds + 60 已覆盖正常时长；超时残留以失去所有权自停收口）；
- Redis 不可用时降级进程内锁（单进程正确；生产 Redis 在位时跨 worker 正确）。
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("agent.run_lock")

LOCK_PREFIX = "agent:runlock:"

# 进程内降级锁（Redis 不可用时的单进程兜底；{key: (owner, expires_at)}）
_memory_locks: dict[str, tuple[str, float]] = {}
_memory_lock_guard = threading.Lock()

_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _key(session_id: int) -> str:
    return f"{LOCK_PREFIX}{session_id}"


def _ttl_seconds(timeout_seconds: int) -> int:
    return int(timeout_seconds) + 60


def acquire_run_lock(session_id: int, trace_id: str, timeout_seconds: int) -> bool:
    """获得同会话执行权；失败即「上一次调用尚未结束」（拒绝新 run）。"""
    ttl = _ttl_seconds(timeout_seconds)
    from app.modules.base.service.cache_service import get_redis_client

    client = get_redis_client()
    if client is not None:
        try:
            return bool(client.set(name=_key(session_id), value=trace_id, ex=ttl, nx=True))
        except Exception as exc:  # noqa: BLE001 —— 连接失败降级进程内锁
            logger.warning("run 锁 Redis 获取失败，降级进程内锁：%s", exc)
    now = time.time()
    with _memory_lock_guard:
        entry = _memory_locks.get(_key(session_id))
        if entry is not None and entry[1] > now:
            return False
        if entry is not None:
            _memory_locks.pop(_key(session_id), None)  # 过期清理
        _memory_locks[_key(session_id)] = (trace_id, now + ttl)
        return True


def release_run_lock(session_id: int, trace_id: str) -> None:
    """安全释放（仅锁值 = 自己 trace_id 才删除）。"""
    from app.modules.base.service.cache_service import get_redis_client

    client = get_redis_client()
    if client is not None:
        try:
            client.eval(_RELEASE_LUA, 1, _key(session_id), trace_id)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("run 锁 Redis 释放失败，清理进程内锁：%s", exc)
    with _memory_lock_guard:
        entry = _memory_locks.get(_key(session_id))
        if entry is not None and entry[0] == trace_id:
            _memory_locks.pop(_key(session_id), None)


def owns_run_lock(session_id: int, trace_id: str) -> bool:
    """所有权校验（run 每步调度前）：锁过期或被他人持有 → False（调用方停止调度并置 cancelled）。"""
    from app.modules.base.service.cache_service import get_redis_client

    client = get_redis_client()
    if client is not None:
        try:
            return client.get(_key(session_id)) == trace_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("run 锁 Redis 校验失败，降级进程内锁：%s", exc)
    with _memory_lock_guard:
        entry = _memory_locks.get(_key(session_id))
        if entry is None:
            return False  # 锁已不存在（过期且未清理）→ 失去所有权
        if entry[1] <= time.time():
            _memory_locks.pop(_key(session_id), None)
            return False
        return entry[0] == trace_id
