import asyncio
import os
import sys
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import redis as redis_core  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password, password_needs_rehash  # noqa: E402
from app.framework.middleware.admin_csrf import AdminCsrfOriginMiddleware  # noqa: E402
from app.framework.middleware.response_envelope import ResponseEnvelopeMiddleware  # noqa: E402
from app.framework.storage import LocalStorageProvider  # noqa: E402
from app.modules.base.service.authority_service import (  # noqa: E402
    is_user_session_allowed,
    register_user_session,
)
from app.modules.base.service.cache_service import cache_delete  # noqa: E402
from app.modules.loader import _handle_module_error  # noqa: E402
from app.modules.task.service.task_invoker import _run_coroutine_sync  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.deleted = []

    def scan_iter(self, match=None, count=None):
        yield from ["a:1", "a:2"]

    def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)


class FrameworkPatchListTests(unittest.TestCase):
    def test_redis_pattern_clear_uses_scan_iter(self):
        old_client = redis_core._redis_client
        fake = FakeRedis()
        redis_core._redis_client = fake
        try:
            redis_core.clear_cache_pattern("a:*")
        finally:
            redis_core._redis_client = old_client
        self.assertEqual(fake.deleted, ["a:1", "a:2"])

    def test_task_invoker_coroutine_runs_inside_existing_loop(self):
        async def sample():
            return "ok"

        async def caller():
            return _run_coroutine_sync(sample())

        self.assertEqual(asyncio.run(caller()), "ok")

    def test_local_storage_rejects_path_traversal_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = os.path.join(temp_dir, "uploads")
            provider = LocalStorageProvider(upload_dir=upload_dir, base_url="/uploads")
            outside = os.path.join(temp_dir, "outside.txt")
            with open(outside, "w", encoding="utf-8") as file:
                file.write("keep")
            self.assertFalse(provider.delete("/uploads/../outside.txt"))
            self.assertTrue(os.path.exists(outside))

    def test_response_envelope_skips_large_json(self):
        old_value = settings.RESPONSE_ENVELOPE_MAX_BYTES
        settings.RESPONSE_ENVELOPE_MAX_BYTES = 16
        app = FastAPI()
        app.add_middleware(ResponseEnvelopeMiddleware)

        @app.get("/large")
        def large():
            return {"text": "x" * 64}

        try:
            response = TestClient(app).get("/large")
        finally:
            settings.RESPONSE_ENVELOPE_MAX_BYTES = old_value
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "x" * 64)

    def test_admin_csrf_origin_check(self):
        old_enabled = settings.ADMIN_CSRF_ORIGIN_CHECK_ENABLED
        old_origins = settings.CORS_ORIGINS
        settings.ADMIN_CSRF_ORIGIN_CHECK_ENABLED = True
        settings.CORS_ORIGINS = '["http://allowed.test"]'
        app = FastAPI()
        app.add_middleware(AdminCsrfOriginMiddleware)

        @app.post("/admin/demo")
        def demo():
            return {"ok": True}

        try:
            client = TestClient(app)
            blocked = client.post("/admin/demo", headers={"origin": "http://blocked.test"})
            allowed = client.post("/admin/demo", headers={"origin": "http://allowed.test"})
        finally:
            settings.ADMIN_CSRF_ORIGIN_CHECK_ENABLED = old_enabled
            settings.CORS_ORIGINS = old_origins
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_password_hash_rehash_policy(self):
        old_iterations = settings.PASSWORD_PBKDF2_ITERATIONS
        settings.PASSWORD_PBKDF2_ITERATIONS = 100_000
        old_hash = hash_password("Passw0rd!")
        settings.PASSWORD_PBKDF2_ITERATIONS = 210_000
        try:
            self.assertTrue(password_needs_rehash(old_hash))
        finally:
            settings.PASSWORD_PBKDF2_ITERATIONS = old_iterations

    def test_session_concurrency_policy(self):
        old_value = settings.ADMIN_SESSION_MAX_CONCURRENT
        settings.ADMIN_SESSION_MAX_CONCURRENT = 1
        user_id = 987654
        cache_delete(f"admin:sessions:{user_id}")
        try:
            register_user_session(user_id, "token-a")
            self.assertTrue(is_user_session_allowed(user_id, "token-a"))
            register_user_session(user_id, "token-b")
            self.assertFalse(is_user_session_allowed(user_id, "token-a"))
            self.assertTrue(is_user_session_allowed(user_id, "token-b"))
        finally:
            cache_delete(f"admin:sessions:{user_id}")
            settings.ADMIN_SESSION_MAX_CONCURRENT = old_value

    def test_module_loader_strict_mode_switch(self):
        old_value = settings.MODULE_LOAD_STRICT
        settings.MODULE_LOAD_STRICT = False
        try:
            with self.assertLogs("app.modules.loader", level="ERROR"):
                _handle_module_error("ignored", RuntimeError("boom"))
            settings.MODULE_LOAD_STRICT = True
            with self.assertRaises(RuntimeError):
                _handle_module_error("raised", RuntimeError("boom"))
        finally:
            settings.MODULE_LOAD_STRICT = old_value


if __name__ == "__main__":
    unittest.main()
