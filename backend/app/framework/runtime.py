"""框架运行时（FastAPI 胶水 + DI 门面）。

M9 定义下沉：RuntimeRegistry / registry / FrameworkRuntimeError 的实现位于
app/core/runtime.py（core 层自洽，core/security 直接消费 core 侧符号）；
本模块保留 FastAPI 相关胶水并门面 re-export 注册表符号，既有引用方
（main 装配点、framework 中间件、controller_meta、守卫探针）import 路径不变。

framework 层不 import 任何业务模块（架构守卫强制）；base 等业务模块在
应用装配期（main.py 顶层，早于路由构建）通过 registry.register 注册实现，
framework 消费侧经 registry.resolve 或下方稳定委托函数获取实现。

- 路由构建时 `Depends(get_current_user)` 只固定 framework 内的委托符号，
  真实实现每请求才解析——注册因此只须早于首个请求（main 顶层早于一切）。
- 未注册即抛 FrameworkRuntimeError（明确失败，绝不静默降级）。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.core.runtime import FrameworkRuntimeError as FrameworkRuntimeError
from app.core.runtime import RuntimeRegistry as RuntimeRegistry
from app.core.runtime import registry as registry

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
