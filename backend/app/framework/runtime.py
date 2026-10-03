"""框架运行时依赖注册表（DI）。

framework 层不 import 任何业务模块（架构守卫强制）；base 等业务模块在
应用装配期（main.py 顶层，早于路由构建）通过 registry.register 注册实现，
framework 消费侧经 registry.resolve 或下方稳定委托函数获取实现。

- 路由构建时 `Depends(get_current_user)` 只固定 framework 内的委托符号，
  真实实现每请求才解析——注册因此只须早于首个请求（main 顶层早于一切）。
- 未注册即抛 FrameworkRuntimeError（明确失败，绝不静默降级）。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session


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

# 与 base 现实现行为等价的 bearer 提取器（无 token 时 credentials 为 None，
# 由注册的实现决定 401/放行语义——不在此处强制报错）
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Any:
    """稳定委托：路由构建只依赖本符号；真实实现由 base 注册（"current_user"）。"""
    return registry.resolve("current_user")(request, credentials, session)
