"""
Base 模块缓存服务
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None
_redis_unavailable = False
_memory_cache: dict[str, tuple[str, float | None]] = {}


@dataclass(frozen=True)
class CacheNamespace:
    """模块级缓存命名空间。"""

    name: str
    default_ttl_seconds: int | None = None

    def key(self, *parts: Any) -> str:
        clean_parts = [str(part).strip(":") for part in parts if part is not None and str(part) != ""]
        return ":".join([self.name, *clean_parts])

    def pattern(self, *parts: Any) -> str:
        return f"{self.key(*parts)}*"

    def set(self, *parts: Any, value: str, ttl_seconds: int | None = None) -> bool:
        return cache_set(self.key(*parts), value, ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds)

    def set_json(self, *parts: Any, value: Any, ttl_seconds: int | None = None) -> bool:
        return cache_set_json(
            self.key(*parts), value, ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        )

    def get(self, *parts: Any) -> str | None:
        return cache_get(self.key(*parts))

    def get_json(self, *parts: Any) -> Any | None:
        return cache_get_json(self.key(*parts))

    def delete(self, *parts: Any) -> None:
        cache_delete(self.key(*parts))

    def clear(self, *parts: Any) -> int:
        return cache_delete_pattern(self.pattern(*parts))


def get_redis_client() -> Redis | None:
    """获取 Redis 客户端，失败时返回 None。"""
    global _redis_client, _redis_unavailable

    if _redis_unavailable:
        return None

    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except RedisError as exc:
            logger.warning("Redis 不可用，将跳过服务端登录态缓存: %s", exc)
            _redis_unavailable = True
            _redis_client = None
            return None

    return _redis_client


def cache_set(key: str, value: str, ttl_seconds: int | None = None) -> bool:
    client = get_redis_client()
    if client is None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        _memory_cache[key] = (value, expires_at)
        return True
    try:
        client.set(name=key, value=value, ex=ttl_seconds)
        return True
    except RedisError as exc:
        logger.warning("Redis 写入失败 %s: %s", key, exc)
        return False


def cache_get(key: str) -> str | None:
    client = get_redis_client()
    if client is None:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and expires_at <= time.time():
            _memory_cache.pop(key, None)
            return None
        return value
    try:
        return client.get(key)
    except RedisError as exc:
        logger.warning("Redis 读取失败 %s: %s", key, exc)
        return None


def cache_delete(*keys: str) -> None:
    client = get_redis_client()
    if not keys:
        return
    if client is None:
        for key in keys:
            _memory_cache.pop(key, None)
        return
    try:
        client.delete(*keys)
    except RedisError as exc:
        logger.warning("Redis 删除失败 %s: %s", ",".join(keys), exc)


def cache_get_del(key: str) -> str | None:
    """原子地读取并删除缓存（Redis GETDEL），用于一次性消费的凭证。

    验证码防重放场景下，原 get+delete 两步操作在并发请求间存在窗口：
    两个请求可能都 get 到同一个验证码后再各自 delete，导致同一验证码被多次消费。
    GETDEL 由 Redis 单线程保证原子，并发请求中仅一个能拿到值。

    Redis 异常或降级到进程内缓存时退化为非原子的 get+delete（单进程下无竞争）。
    """
    client = get_redis_client()
    if client is not None:
        try:
            return client.getdel(key)
        except RedisError as exc:
            logger.warning("Redis GETDEL 失败 %s: %s（退化为 get+delete）", key, exc)
    value = cache_get(key)
    cache_delete(key)
    return value


def cache_delete_pattern(pattern: str) -> int:
    """按模式删除缓存，Redis 使用 SCAN，内存降级使用 fnmatch。"""
    from fnmatch import fnmatch

    client = get_redis_client()
    deleted = 0
    if client is None:
        for key in list(_memory_cache.keys()):
            if fnmatch(key, pattern):
                _memory_cache.pop(key, None)
                deleted += 1
        return deleted
    try:
        batch: list[str] = []
        for key in client.scan_iter(match=pattern, count=500):
            batch.append(key)
            if len(batch) >= 500:
                deleted += client.delete(*batch)
                batch.clear()
        if batch:
            deleted += client.delete(*batch)
    except RedisError as exc:
        logger.warning("Redis 按模式删除失败 %s: %s", pattern, exc)
    return deleted


def cache_set_json(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    return cache_set(key, json.dumps(value, ensure_ascii=True), ttl_seconds)


def cache_set_nx(key: str, value: str, ttl_seconds: int | None = None) -> bool:
    """SETNX 语义：仅当 key 不存在时设置。成功返回 True，已存在返回 False。

    用于防重放锁（如 task once() 高频去重）。Redis 异常时 fail-open 放行
    （返回 True），与 cache_incr 的降级策略一致，避免 Redis 抖动阻断业务。
    """
    client = get_redis_client()
    if client is not None:
        try:
            result = client.set(name=key, value=value, ex=ttl_seconds, nx=True)
            return bool(result)
        except RedisError as exc:
            logger.warning("Redis SETNX 失败 %s: %s（降级放行）", key, exc)
            return True
    # 内存降级：检查存在性后设置（单进程下无竞争）
    entry = _memory_cache.get(key)
    if entry is not None:
        _, expires_at = entry
        if expires_at is not None and expires_at <= time.time():
            _memory_cache.pop(key, None)
        else:
            return False
    expires_at = time.time() + ttl_seconds if ttl_seconds else None
    _memory_cache[key] = (value, expires_at)
    return True


def cache_incr(key: str, ttl_seconds: int | None = None) -> int | None:
    """
    原子递增计数器。返回递增后的值；Redis 异常时返回 None 表示计数不可靠。

    调用方应对 None 做 fail-open 处理（放行并告警），避免 Redis 抖动时治理/限流
    基于不可靠计数误判（多进程下内存降级计数分散，会超限放行）。
    Redis 未配置（开发环境）仍降级为进程内内存计数。
    """
    client = get_redis_client()
    if client is not None:
        try:
            pipe = client.pipeline(transaction=True)
            pipe.incr(key)
            if ttl_seconds is not None:
                pipe.expire(key, ttl_seconds)
            results = pipe.execute()
            return results[0]
        except RedisError as exc:
            logger.error("Redis INCR 失败 %s: %s（计数不可靠，调用方应 fail-open 放行）", key, exc)
            return None

    # 降级：内存缓存（单进程下无竞争）
    entry = _memory_cache.get(key)
    if entry is not None:
        value, _ = entry
        current = int(value) + 1
    else:
        current = 1
    expires_at = time.time() + ttl_seconds if ttl_seconds else None
    _memory_cache[key] = (str(current), expires_at)
    return current


def cache_decr(key: str, ttl_seconds: int | None = None) -> int:
    """
    原子递减计数器，结果不低于 0。返回递减后的值。
    与 cache_incr 配对使用，Redis 不可用时降级为非原子的 get+set（单进程下可接受）。
    """
    client = get_redis_client()
    if client is not None:
        try:
            pipe = client.pipeline(transaction=True)
            pipe.decr(key)
            if ttl_seconds is not None:
                pipe.expire(key, ttl_seconds)
            current = pipe.execute()[0]
            if current < 0:
                client.set(key, 0, ex=ttl_seconds)
                current = 0
            return current
        except RedisError as exc:
            logger.warning("Redis DECR 失败 %s: %s", key, exc)

    # 降级：内存缓存（单进程下无竞争），结果不低于 0
    entry = _memory_cache.get(key)
    if entry is not None:
        value, _ = entry
        current = max(0, int(value) - 1)
    else:
        current = 0
    expires_at = time.time() + ttl_seconds if ttl_seconds else None
    _memory_cache[key] = (str(current), expires_at)
    return current


def cache_get_json(key: str) -> Any | None:
    value = cache_get(key)
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Redis JSON 解析失败 %s", key)
        return None
