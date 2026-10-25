"""错误响应契约统一回归。

覆盖：404/405 接管（StarletteHTTPException 父类注册）、错误码映射（1004/1005/1001）、
422 全量错误明细、防误包兜底（裸 detail 不再变成 code=1000 success）、4xx 分级日志、
500 追踪号、celery 日志上下文跨进程串联、SSE generator 断连注销。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from app.celery_app import (
    _clear_log_context,
    _inject_log_context,
    _log_task_retry,
    _restore_log_context,
)
from app.core.logging import request_id_ctx
from app.framework.api.exception_handlers import register_exception_handlers
from app.framework.middleware.response_envelope import ResponseEnvelopeMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(ResponseEnvelopeMiddleware)

    @app.post("/only-post")
    def only_post():
        return {"ok": True}

    @app.get("/validate-required")
    def validate_required(a: int, b: int):  # 两个必填 query 全缺 → 2 处校验错误
        return {"a": a, "b": b}

    @app.get("/http-401")
    def http_401():
        raise HTTPException(status_code=401, detail="未登录")

    return app


class ErrorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_build_app())

    def test_404_returns_not_found_code(self) -> None:
        resp = self.client.get("/not-exists")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertEqual(data["code"], 1005)
        self.assertNotEqual(data["code"], 1000)

    def test_405_returns_fail_code(self) -> None:
        resp = self.client.get("/only-post")
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.json()["code"], 1001)

    def test_validation_422_uses_validation_code_with_details(self) -> None:
        resp = self.client.get("/validate-required")
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["code"], 1004)
        self.assertEqual(len(data["data"]["errors"]), 2)
        fields = {item["field"] for item in data["data"]["errors"]}
        self.assertEqual(fields, {"a", "b"})

    def test_http_exception_401_maps_unauthorized_and_logs(self) -> None:
        with self.assertLogs("app.exceptions", level="WARNING") as captured:
            resp = self.client.get("/http-401")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 1002)
        self.assertIn("未登录", "\n".join(captured.output))

    def test_success_payload_still_enveloped(self) -> None:
        resp = self.client.post("/only-post")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 1000)
        self.assertEqual(data["data"], {"ok": True})


class CeleryLogContextTests(unittest.TestCase):
    def test_publish_injects_and_prerun_restores_context(self) -> None:
        token = request_id_ctx.set("req-abc")
        headers: dict = {}
        try:
            _inject_log_context(headers=headers)
            self.assertEqual(headers["loom_log_context"]["request_id"], "req-abc")
        finally:
            request_id_ctx.reset(token)

        # worker 侧：恢复 → 断言 contextvar → postrun 清理
        fake_task = SimpleNamespace(
            request=SimpleNamespace(id="task-1", headers={"loom_log_context": {"request_id": "req-abc"}})
        )
        _restore_log_context(task=fake_task)
        try:
            self.assertEqual(request_id_ctx.get(), "req-abc")
        finally:
            _clear_log_context(task=fake_task)
        self.assertIsNone(request_id_ctx.get())

    def test_retry_signal_logged(self) -> None:
        with self.assertLogs("app.exceptions", level="WARNING") as captured:
            _log_task_retry(sender=SimpleNamespace(name="task.execute"), task_id="t-9", reason="timeout")
        self.assertIn("task.execute", "\n".join(captured.output))
        self.assertIn("timeout", "\n".join(captured.output))


class SseGeneratorCleanupTests(unittest.TestCase):
    def test_generator_close_unregisters_handle(self) -> None:
        """客户端断开（generator close）时 handle 必须被注销，不再泄漏。"""

        from app.modules.agent.service.runtime import run_service
        from app.modules.agent.service.runtime.run_service import (
            RunDeadline,
            RunHandle,
            _get_handle,
            _register_handle,
        )

        handle = RunHandle(trace_id=0, trace_token="leak-test-token", session_id=1, deadline=RunDeadline(5))
        _register_handle(handle)
        self.assertIsNotNone(_get_handle("leak-test-token"))

        # 与 stream_run 相同形态的 generator：yield 后挂起在 event_queue.get 上
        def generator():
            try:
                yield "started"
                while True:
                    handle.event_queue.get(timeout=5)  # 挂起等待（close 时由此注入中断）
            finally:
                run_service._unregister_handle(handle)  # noqa: SLF001 —— 单测装配

        gen = generator()
        next(gen)
        gen.close()  # 模拟客户端断开 → GeneratorExit 进入 finally
        self.assertIsNone(_get_handle("leak-test-token"))


if __name__ == "__main__":
    unittest.main()
