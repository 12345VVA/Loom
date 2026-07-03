"""
Task 1.1: aiapi scope 增加 AI 调用权限校验（P0-1）

验证：
- 未授权用户（无 AI 调用权限）调用各 AI 接口返回 403
- 授权用户（超管）可正常调用 AI 接口
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session as DbSession, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.modules.base.model.auth import User  # noqa: E402
from app.modules.base.service.authority_service import clear_login_caches  # noqa: E402
from app.modules.base.service.cache_service import cache_delete_pattern  # noqa: E402
from app.modules.base.service.security_service import create_access_token  # noqa: E402
from main import app  # noqa: E402


class AiApiPermissionTests(unittest.TestCase):
    """验证 aiapi scope AI 调用权限校验。"""

    TEST_USERNAME = "test_ai_no_perm_user"

    def setUp(self):
        cache_delete_pattern("login:fail:*")
        cache_delete_pattern("login:lock:*")
        self.client = TestClient(app)
        self.client.__enter__()

        # 创建一个普通用户（无角色、无 AI 调用权限）
        with DbSession(engine) as session:
            existing = session.exec(select(User).where(User.username == self.TEST_USERNAME)).first()
            if existing:
                clear_login_caches(existing.id)
                session.delete(existing)
                session.commit()

            self.normal_user = User(
                username=self.TEST_USERNAME,
                full_name="Test No Permission",
                password_hash=hash_password("test-password-123"),
                is_active=True,
                is_super_admin=False,
            )
            session.add(self.normal_user)
            session.commit()
            session.refresh(self.normal_user)
            self.normal_user_id = self.normal_user.id

    def tearDown(self):
        # 清理测试用户
        with DbSession(engine) as session:
            user = session.get(User, self.normal_user_id)
            if user:
                clear_login_caches(user.id)
                session.delete(user)
                session.commit()
        self.client.__exit__(None, None, None)

    def _slider_verify_code(self, captcha_data: dict) -> str:
        target_x = int(captcha_data["data"]["targetX"])
        return json.dumps(
            {
                "x": target_x,
                "duration": 720,
                "track": [{"x": round(target_x * step / 6, 2), "t": step * 120} for step in range(1, 7)],
            }
        )

    def _admin_headers(self) -> dict[str, str]:
        """登录超管账号获取 Authorization 头。"""
        captcha_res = self.client.get("/admin/base/open/captcha")
        self.assertEqual(captcha_res.status_code, 200)
        captcha_data = captcha_res.json()["data"]
        login_res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "captchaId": captcha_data["captchaId"],
                "verifyCode": self._slider_verify_code(captcha_data),
            },
        )
        self.assertEqual(login_res.status_code, 200)
        return {"Authorization": f"Bearer {login_res.json()['data']['token']}"}

    def _normal_user_headers(self) -> dict[str, str]:
        """为无权限的普通用户生成 access token。"""
        with DbSession(engine) as session:
            user = session.get(User, self.normal_user_id)
            self.assertIsNotNone(user)
            token = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # 未授权用户（无 AI 调用权限）调用各 AI 接口应返回 403
    # ------------------------------------------------------------------

    def test_unauthorized_user_chat_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/chat",
                headers=headers,
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_stream_chat_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/streamChat",
                headers=headers,
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_embedding_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/embedding",
                headers=headers,
                json={"input": "test"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_image_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/image",
                headers=headers,
                json={"prompt": "draw a cat"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_rerank_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/rerank",
                headers=headers,
                json={"query": "test", "documents": ["doc1", "doc2"]},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_audio_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/audio",
                headers=headers,
                json={"input": "test"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    def test_unauthorized_user_video_returns_403(self):
        headers = self._normal_user_headers()
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            response = self.client.post(
                "/aiapi/ai/model/video",
                headers=headers,
                json={"prompt": "test"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("无 AI 调用权限", response.json()["message"])
        mock_service.assert_not_called()

    # ------------------------------------------------------------------
    # 授权用户（超管）调用 AI 接口应正常通过权限校验
    # ------------------------------------------------------------------

    def test_authorized_admin_chat_passes_permission_check(self):
        headers = self._admin_headers()
        expected = {"success": True, "content": "ok"}
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            mock_service.return_value.chat.return_value = expected
            response = self.client.post(
                "/aiapi/ai/model/chat",
                headers=headers,
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(response.status_code, 200)
        mock_service.return_value.chat.assert_called_once()

    def test_authorized_admin_embedding_passes_permission_check(self):
        headers = self._admin_headers()
        expected = {"success": True, "data": [0.1, 0.2]}
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            mock_service.return_value.embedding.return_value = expected
            response = self.client.post(
                "/aiapi/ai/model/embedding",
                headers=headers,
                json={"input": "test"},
            )
        self.assertEqual(response.status_code, 200)
        mock_service.return_value.embedding.assert_called_once()

    def test_authorized_admin_rerank_passes_permission_check(self):
        headers = self._admin_headers()
        expected = {"success": True, "results": []}
        with patch("app.modules.ai.controller.aiapi.model.AiModelRuntimeService") as mock_service:
            mock_service.return_value.rerank.return_value = expected
            response = self.client.post(
                "/aiapi/ai/model/rerank",
                headers=headers,
                json={"query": "test", "documents": ["doc1"]},
            )
        self.assertEqual(response.status_code, 200)
        mock_service.return_value.rerank.assert_called_once()


if __name__ == "__main__":
    unittest.main()
