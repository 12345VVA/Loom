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
from app.framework.middleware.request_id import RequestIdMiddleware
from app.framework.middleware.response_envelope import ResponseEnvelopeMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    # 模拟真实链的内外序（Envelope 在 RequestId 外侧），500 追踪号依赖
    # RequestIdMiddleware 写入的 request.state.request_id
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(ResponseEnvelopeMiddleware)

    @app.post("/only-post")
    def only_post():
        return {"ok": True}

    @app.get("/validate-required")
    def validate_required(a: int, b: int):  # 两个必填 query 全缺 → 2 处校验错误
        return {"a": a, "b": b}

    @app.get("/validate-single")
    def validate_single(a: int):  # 单个必填 query 缺失 → 1 处校验错误
        return {"a": a}

    @app.get("/http-401")
    def http_401():
        raise HTTPException(status_code=401, detail="未登录")

    @app.get("/boom")
    def boom():
        raise RuntimeError("数据库连接炸了")

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

    def test_validation_422_single_error_also_has_details(self) -> None:
        """单条校验错误同样返回结构化明细（1 条与 N 条契约一致）。"""
        resp = self.client.get("/validate-single")
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["code"], 1004)
        self.assertEqual(len(data["data"]["errors"]), 1)
        self.assertEqual(data["data"]["errors"][0]["field"], "a")

    def test_404_logs_at_debug_level(self) -> None:
        """404 在 DEBUG 级别开启时必须有且仅有日志（分级降噪≠完全不记）。"""
        with self.assertLogs("app.exceptions", level="DEBUG") as captured:
            resp = self.client.get("/not-exists")
        self.assertEqual(resp.status_code, 404)
        http_logs = [line for line in captured.output if "HTTP 404" in line]
        self.assertEqual(len(http_logs), 1)
        # 响应侧给全局中文文案
        self.assertEqual(resp.json()["message"], "路由不存在")

    def test_500_message_carries_trace_id_when_not_debug(self) -> None:
        """非 DEBUG 下 500 响应 message 必须带追踪号（报障截图可与 error.log 对账）。"""
        from app.core.config import settings

        client = TestClient(_build_app(), raise_server_exceptions=False)
        saved = settings.DEBUG
        settings.DEBUG = False
        try:
            with self.assertLogs("app.exceptions", level="ERROR"):
                resp = client.get("/boom")
        finally:
            settings.DEBUG = saved
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["code"], 1050)  # SERVER_ERROR：与 4xx 的 FAIL(1001) 可区分
        self.assertIn("追踪号", resp.json()["message"])

    def test_business_error_returns_envelope(self) -> None:
        """BusinessError（渐进式业务异常基类）转 error envelope，不打堆栈。"""
        from app.framework.api.errors import BusinessError

        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/closed")
        def closed():
            raise BusinessError("工单已关闭，无法撤回", code=1006, status_code=409)

        client = TestClient(app)
        resp = client.get("/closed")
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data["code"], 1006)
        self.assertEqual(data["message"], "工单已关闭，无法撤回")

    def test_non_json_error_response_normalized(self) -> None:
        """非 JSON 错误（网关注入 text/plain）也兜底为 error envelope。"""
        from starlette.responses import PlainTextResponse

        app = FastAPI()
        register_exception_handlers(app)
        app.add_middleware(ResponseEnvelopeMiddleware)

        @app.get("/plain-403")
        def plain_403():
            return PlainTextResponse("Forbidden by gateway", status_code=403)

        client = TestClient(app)
        resp = client.get("/plain-403")
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data["code"], 1003)
        self.assertEqual(data["message"], "Forbidden by gateway")

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

    def test_beat_task_gets_fallback_request_id(self) -> None:
        """beat/无来源任务兜底生成 celery:{task_id} 追踪号，worker 日志可按任务检索。"""
        fake_task = SimpleNamespace(request=SimpleNamespace(id="abc-123", headers={}))
        _restore_log_context(task=fake_task)
        try:
            self.assertEqual(request_id_ctx.get(), "celery:abc-123")
        finally:
            _clear_log_context(task=fake_task)
        self.assertIsNone(request_id_ctx.get())

    def test_prerun_clears_stale_tokens_for_same_task_id(self) -> None:
        """postrun 异常路径未执行时，同 id 重跑的 prerun 必须先清残留再兜底。"""
        from app.celery_app import _TASK_CONTEXT_TOKENS

        fake_task = SimpleNamespace(request=SimpleNamespace(id="stale-1", headers={}))
        # 模拟上一轮执行残留：token 登记在 dict 里（真实现场由 prerun 写入）
        stale_token = request_id_ctx.set("stale")
        _TASK_CONTEXT_TOKENS["stale-1"] = [(request_id_ctx, stale_token)]
        try:
            _restore_log_context(task=fake_task)
            # 残留的 "stale" 被清掉，重新兜底为任务级追踪号
            self.assertEqual(request_id_ctx.get(), "celery:stale-1")
        finally:
            _clear_log_context(task=fake_task)


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
