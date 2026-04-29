import redis
from app.core.config import settings

# 全局 Redis 客户端引用
_redis_client = None


def get_redis():
    """获取 Redis 客户端单例"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def clear_cache(key: str):
    """清除指定缓存"""
    get_redis().delete(key)


def clear_cache_pattern(pattern: str):
    """根据模式清除缓存"""
    r = get_redis()
    batch: list[str] = []
    for key in r.scan_iter(match=pattern, count=500):
        batch.append(key)
        if len(batch) >= 500:
            r.delete(*batch)
            batch.clear()
    if batch:
        r.delete(*batch)

# 便于直接导入使用的实例 (单例包装)
class RedisClientProxy:
    def __getattr__(self, name):
        return getattr(get_redis(), name)

redis_client = RedisClientProxy()
