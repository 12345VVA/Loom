"""中间件拓扑断言：固化两轮错误处理整改后的链路顺序，防回归。

starlette `add_middleware` 为前插（后加者在链更外层），因此 `app.user_middleware`
的最终顺序即请求经过的「外层 → 内层」。本测试锁定三条关键性质：

1. 异常兜底（ExceptionGuard）必须包住全部业务中间件——中间件/流式协程异常
   才能被规范化记录而非冒到 uvicorn 打脏堆栈；
2. BodyBuffer（请求体分片合并）必须包住全部 BaseHTTPMiddleware——否则残余
   分片再次击穿 SSE 断连监听链；
3. CORS 在最外（异常响应可补 CORS 头），鉴权三件套在最内（紧贴路由）。
"""

from __future__ import annotations

import unittest

from starlette.middleware.cors import CORSMiddleware

from app.framework.middleware.body_buffer import BodyBufferMiddleware
from app.framework.middleware.exception_guard import ExceptionGuardMiddleware
from app.framework.middleware.module_runtime import PrefixScopedMiddleware
from app.framework.middleware.request_id import RequestIdMiddleware
from app.framework.middleware.response_envelope import ResponseEnvelopeMiddleware
from app.framework.middleware.scope_authority import (
    AdminAuthorityMiddleware,
    AiApiAuthorityMiddleware,
    AppAuthorityMiddleware,
)
from main import app  # noqa: E402 —— 导入期副作用（路由注册/EPS）为既有测试接受的形态


class MiddlewareTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        # PrefixScoped 按模块绑定展开（每绑定一层），测试里折叠为「模块:中间件」可读名
        self.chain: list[str] = []
        for mw in app.user_middleware:
            if mw.cls is PrefixScopedMiddleware:
                inner = (mw.kwargs or {}).get("middleware_cls")
                module = (mw.kwargs or {}).get("module_name", "?")
                self.chain.append(f"{module}:{getattr(inner, '__name__', inner)}")
            else:
                self.chain.append(mw.cls.__name__)

    def test_outermost_three_layers(self) -> None:
        """CORS 最外 → 异常兜底 → 请求体合并。"""
        self.assertEqual(self.chain[0], CORSMiddleware.__name__)
        self.assertEqual(self.chain[1], ExceptionGuardMiddleware.__name__)
        self.assertEqual(self.chain[2], BodyBufferMiddleware.__name__)

    def test_full_order(self) -> None:
        """全链顺序（外→内）：CORS/兜底/合并 → 全局九层 → 模块绑定层 → 鉴权三件套。

        全局九层序：RequestId → Metrics → RateLimit → AdminCsrf → ResponseEnvelope
        → OperationLog → AiApi → App → Admin。
        """
        non_prefix = [name for name in self.chain if ":" not in name]
        self.assertEqual(
            non_prefix,
            [
                CORSMiddleware.__name__,
                ExceptionGuardMiddleware.__name__,
                BodyBufferMiddleware.__name__,
                RequestIdMiddleware.__name__,
                "MetricsMiddleware",
                "RateLimitMiddleware",
                "AdminCsrfOriginMiddleware",
                ResponseEnvelopeMiddleware.__name__,
                "OperationLogMiddleware",
                AiApiAuthorityMiddleware.__name__,
                AppAuthorityMiddleware.__name__,
                AdminAuthorityMiddleware.__name__,
            ],
        )

    def test_authority_innermost(self) -> None:
        """鉴权三件套紧贴路由（最内三层）。"""
        self.assertEqual(self.chain[-1], AdminAuthorityMiddleware.__name__)
        self.assertEqual(self.chain[-2], AppAuthorityMiddleware.__name__)
        self.assertEqual(self.chain[-3], AiApiAuthorityMiddleware.__name__)

    def test_operation_log_is_pure_asgi(self) -> None:
        """OperationLog 必须保持纯 ASGI（非 BaseHTTPMiddleware）。

        根因锁（真机实测）：BaseHTTPMiddleware 形态下 dispatch 预读 body 的
        ``request._body`` 缓存会让 wrapped_receive 在 SSE 挂起期的断连监听链中
        永远返回合成 http.request，击穿整条监听链——所有 SSE 流必崩（表现为
        「每次对话都慢」：前端只能等超时后靠 trace 兜底拉回复）。任何人把它改回
        BaseHTTPMiddleware 或在 BaseHTTPMiddleware 中预读 body 都会复发。
        """
        from starlette.middleware.base import BaseHTTPMiddleware

        from app.framework.middleware.operation_log import OperationLogMiddleware

        self.assertFalse(issubclass(OperationLogMiddleware, BaseHTTPMiddleware))


if __name__ == "__main__":
    unittest.main()
