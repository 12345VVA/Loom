"""
模块运行时中间件桥接
"""

from __future__ import annotations

from starlette.types import Receive, Scope, Send


class PrefixScopedMiddleware:
    """模块级中间件的前缀桥接壳（评审 F8：纯 ASGI）。

    前缀命中时调用内层中间件的**完整 ``__call__``**（含其异常处理与响应封装），
    未命中直通。旧实现继承 BaseHTTPMiddleware 且手动调 ``inner.dispatch``——
    绕开内层封装链、外壳自身又多一层每请求 task-group。

    ``request.state`` 底层即 ``scope["state"]``（RequestId 中间件同款先例），
    ``module_name`` 经此注入。注册经 ``add_middleware``（kwargs 键名
    ``middleware_cls``/``module_name``），拓扑断言依赖该形态。
    """

    def __init__(self, app, *, middleware_cls, prefixes: tuple[str, ...], module_name: str):
        self.app = app
        self._middleware = middleware_cls(app)
        self._prefixes = tuple(prefix.rstrip("/") or "/" for prefix in prefixes)
        self._module_name = module_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = (scope.get("path") or "").rstrip("/") or "/"
        if not any(path.startswith(prefix) for prefix in self._prefixes):
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})["module_name"] = self._module_name
        await self._middleware(scope, receive, send)
