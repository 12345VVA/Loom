"""AI 治理告警 registry 回调解耦测试（2026-10-18 批次2）。

覆盖 _notify_once 三分支：回调成功（True）/ 回调抛错降级（False）/ 未注册降级（False），
以及 warn→warning 的 level 映射。registry 以 mock 替换，不污染全局单例。
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel

from app.core.runtime import FrameworkRuntimeError
from app.modules.ai.model.ai import AiGovernanceRule
from app.modules.ai.service.governance_service import (
    GOVERNANCE_ALERT_CALLBACK,
    AiGovernanceService,
)


class AiGovernanceAlertTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.rule = AiGovernanceRule(
            code="alert-rule", name="Alert Rule", scope_type="global", period="day", max_requests=1, is_active=True
        )
        self.session.add(self.rule)
        self.session.commit()
        self.session.refresh(self.rule)
        self.service = AiGovernanceService(self.session)
        self.window_start = datetime(2026, 10, 18, tzinfo=UTC)
        self.window_end = datetime(2026, 10, 19, tzinfo=UTC)

    def tearDown(self):
        self.session.close()

    def _notify(self, *, event_type: str = "blocked"):
        return self.service._notify_once(
            self.rule,
            metric="request",
            event_type=event_type,
            window_start=self.window_start,
            window_end=self.window_end,
            message="请求超限",
        )

    def test_notify_invokes_registered_callback_with_business_params(self):
        callback = Mock(return_value=True)
        with patch("app.modules.ai.service.governance_service.registry") as registry_mock:
            registry_mock.resolve.return_value = callback
            self.assertTrue(self._notify())

        registry_mock.resolve.assert_called_once_with(GOVERNANCE_ALERT_CALLBACK)
        kwargs = callback.call_args.kwargs
        self.assertEqual(kwargs["message"], "请求超限")
        self.assertEqual(kwargs["level"], "error")  # blocked → error
        self.assertIn(f"{self.rule.id}:request:blocked:", kwargs["business_key"])

    def test_notify_maps_warn_event_to_warning_level(self):
        callback = Mock(return_value=True)
        with patch("app.modules.ai.service.governance_service.registry") as registry_mock:
            registry_mock.resolve.return_value = callback
            self.assertTrue(self._notify(event_type="warn"))

        self.assertEqual(callback.call_args.kwargs["level"], "warning")

    def test_notify_degrades_when_callback_raises(self):
        callback = Mock(side_effect=RuntimeError("send failed"))
        with patch("app.modules.ai.service.governance_service.registry") as registry_mock:
            registry_mock.resolve.return_value = callback
            self.assertFalse(self._notify())

    def test_notify_degrades_when_callback_unregistered(self):
        with patch("app.modules.ai.service.governance_service.registry") as registry_mock:
            registry_mock.resolve.side_effect = FrameworkRuntimeError("未注册")
            self.assertFalse(self._notify())

    def test_notify_dedup_skips_when_already_notified(self):
        self.service._event(
            rule=self.rule,
            user_id=None,
            profile=Mock(id=1),
            model=Mock(id=1),
            provider=Mock(id=1),
            event_type="blocked",
            metric="request",
            current=2,
            limit=1,
            window_start=self.window_start,
            window_end=self.window_end,
            message="请求超限",
            notified=True,
        )
        callback = Mock(return_value=True)
        with patch("app.modules.ai.service.governance_service.registry") as registry_mock:
            registry_mock.resolve.return_value = callback
            self.assertFalse(self._notify())

        registry_mock.resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
