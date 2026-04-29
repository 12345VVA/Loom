import hashlib
import json
import functools
from typing import Any, Callable, TypeVar

from app.core.redis import get_redis
from app.modules.base.service.cache_service import cache_delete_pattern

F = TypeVar("F", bound=Callable[..., Any])


def CoolCache(ttl: int = 3600, key_prefix: str = "cache", namespace: str | None = None):
    """
    通用 Redis 缓存装饰器。
    用法:
        @CoolCache(ttl=7200)
        def get_data(self, param1, param2):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取 redis 客户端
            redis_client = get_redis()
            
            # 构造唯一的缓存 Key
            # 跳过 self 参数 (args[0] 通常是 service 实例)
            relevant_args = args[1:] if args and hasattr(args[0], "__class__") else args
            
            arg_str = json.dumps(
                {"args": [str(a) for a in relevant_args], "kwargs": kwargs}, 
                sort_keys=True
            )
            arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
            cache_namespace = namespace or f"{func.__module__}.{func.__qualname__}"
            cache_key = f"{key_prefix}:{cache_namespace}:{arg_hash}"
            
            # 尝试从缓存获取
            cached_val = redis_client.get(cache_key)
            if cached_val:
                try:
                    return json.loads(cached_val)
                except:
                    return cached_val
            
            # 执行原始方法
            result = func(*args, **kwargs)
            
            # 异步执行的话需要特殊处理，这里暂时假设同步
            # 如果 result 是 pydantic 模型，转为 json
            serialized = result
            if hasattr(result, "model_dump"):
                serialized = result.model_dump(mode="json")
            elif isinstance(result, list):
                serialized = [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in result]
            
            # 存入缓存
            redis_client.setex(cache_key, ttl, json.dumps(serialized))
            
            return result

        return wrapper

    return decorator


def clear_cool_cache(namespace: str = "*", key_prefix: str = "cache") -> int:
    """清理 CoolCache 命名空间缓存。"""
    return cache_delete_pattern(f"{key_prefix}:{namespace}:*")
