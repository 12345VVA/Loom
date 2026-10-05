"""核心层运行时依赖注册表（DI）。

M9 定义下沉：注册表为纯 stdlib 实现，归属 core 层；framework/runtime.py
保留 FastAPI 胶水（bearer 提取、get_current_user 稳定委托）并门面 re-export
本模块符号。framework 层不 import 任何业务模块（架构守卫强制）；base 等
业务模块在应用装配期（main.py 顶层，早于路由构建）通过 registry.register
注册实现，消费侧经 registry.resolve 获取实现。

- 未注册即抛 FrameworkRuntimeError（明确失败，绝不静默降级）。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class FrameworkRuntimeError(RuntimeError):
    """框架运行时依赖缺失（业务模块未完成装配）。"""


class RuntimeRegistry:
    """线程安全的名字 → 实现注册表（controller_meta 注册表同款范式）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._impls: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, impl: Callable[..., Any]) -> None:
        with self._lock:
            self._impls[name] = impl

    def resolve(self, name: str) -> Callable[..., Any]:
        with self._lock:
            impl = self._impls.get(name)
        if impl is None:
            raise FrameworkRuntimeError(
                f"框架运行时依赖未注册: {name}（业务模块装配缺失，检查应用入口的 registry.register）"
            )
        return impl


registry = RuntimeRegistry()
