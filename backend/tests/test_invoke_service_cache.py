"""_invoke_service 签名反射缓存测试（评审 F11）。

此前每个请求对 service 方法执行一次 inspect.signature。缓存键必须是
`method.__func__`（类级函数）：`meta.service(session)` 每请求新建实例，绑定方法
对象每请求都是新的，直接缓存 method 永不命中且持引用泄漏。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.framework.controller_meta import _invoke_service, _signature_param_names  # noqa: E402


class InvokeServiceCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        _signature_param_names.cache_clear()

    def test_filters_kwargs_by_signature(self):
        class Service:
            def page(self, query, request=None):
                return {"query": query, "request": request}

        result = _invoke_service(Service().page, query="q", current_user="u", session="s")
        self.assertEqual(result, {"query": "q", "request": None})

    def test_cache_hits_across_instances(self):
        """不同实例的同名方法共享底层函数 → 只反射一次。"""

        class Service:
            def handler(self, query):
                return query

        first = _invoke_service(Service().handler, query=1, extra=2)
        second = _invoke_service(Service().handler, query=3, extra=4)
        info = _signature_param_names.cache_info()
        self.assertEqual((first, second), (1, 3))
        self.assertEqual(info.misses, 1)
        self.assertEqual(info.hits, 1)

    def test_plain_function_without_binding(self):
        func = lambda query: query  # noqa: E731 —— 无 __func__ 的裸函数走 getattr 兜底分支
        self.assertEqual(_invoke_service(func, query=5, extra=1), 5)

    def test_zero_arg_callables_receive_nothing(self):
        class Service:
            def noop(self):
                return "ok"

        self.assertEqual(_invoke_service(Service().noop, query=1), "ok")


if __name__ == "__main__":
    unittest.main()
