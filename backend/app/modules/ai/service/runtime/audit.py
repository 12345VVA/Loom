"""治理收尾与调用审计日志（AI-013 拆分，纯搬迁）。_log_call 是全模块唯一写点。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlmodel import Session

from app.core.logging import workflow_instance_id_ctx
from app.modules.ai.model.ai import AiModel, AiModelCallLog, AiModelProfile, AiProvider
from app.modules.ai.service.runtime.common import _InvocationState
from app.modules.ai.service.stats_service import invalidate_summary_cache
from app.modules.ai.service.utils import sanitize_options_for_log
from app.modules.base.model.auth import User

logger = logging.getLogger(__name__)


class AuditMixin:
    def _audit_success(
        self,
        st: _InvocationState,
        usage: dict[str, Any],
        *,
        session: Session,
        user: User | None,
        cost_micro_usd: int,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理收尾（success）+ 成功审计日志，并标记 closed。"""
        st.governance.finish(
            st.invocation,
            status_value="success",
            user=user,
            provider=st.provider,
            model=st.model,
            profile=st.profile,
            usage=usage,
            cost_micro_usd=cost_micro_usd,
        )
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            "success",
            st.start,
            usage,
            user=user,
            cost_micro_usd=cost_micro_usd,
            request_id=request_id,
            options=options,
            session=session,
            task_id=st.task_id,
        )

    def _audit_failure(
        self,
        st: _InvocationState,
        status_value: str,
        usage: dict[str, Any],
        detail: str | None,
        *,
        session: Session,
        user: User | None,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理收尾（指定状态，cost=0）+ 失败审计日志，并标记 closed。"""
        st.governance.finish(
            st.invocation,
            status_value=status_value,
            user=user,
            provider=st.provider,
            model=st.model,
            profile=st.profile,
            usage=usage,
            cost_micro_usd=0,
        )
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            status_value,
            st.start,
            usage,
            detail,
            user=user,
            request_id=request_id,
            options=options,
            session=session,
            task_id=st.task_id,
        )

    def _block_invocation(
        self,
        st: _InvocationState,
        status_value: str,
        usage: dict[str, Any],
        detail: str,
        *,
        session: Session,
        user: User | None,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """治理阻断（block_invocation，用于 Redis 故障 fail-closed / 规则拦截）+ 审计日志。"""
        st.governance.block_invocation(st.invocation)
        st.closed = True
        self._log_call(
            st.provider,
            st.model,
            st.profile,
            status_value,
            st.start,
            usage,
            detail,
            user=user,
            request_id=request_id,
            options=options,
            session=session,
            task_id=st.task_id,
        )

    def _log_call(
        self,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
        status_value: str,
        start: float,
        usage: dict,
        error: str | None = None,
        *,
        session: Session,
        user: User | None = None,
        cost_micro_usd: int = 0,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
        task_id: int | None = None,
    ) -> None:
        request_options_str: str | None = None
        if options:
            try:
                request_options_str = json.dumps(sanitize_options_for_log(options), ensure_ascii=False)
            except Exception:
                pass

        log = AiModelCallLog(
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            user_id=user.id if user else None,
            scenario=profile.scenario,
            model_type=model.model_type,
            status=status_value,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=int(usage.get("promptTokens") or 0),
            completion_tokens=int(usage.get("completionTokens") or 0),
            total_tokens=int(usage.get("totalTokens") or 0),
            cost_micro_usd=cost_micro_usd,
            currency="USD",
            error_message=(error or "")[:500] or None,
            request_id=request_id,
            workflow_instance_id=workflow_instance_id_ctx.get(),
            task_id=task_id,
            request_options=request_options_str,
        )
        session.add(log)
        session.commit()
        # 失效统计看板缓存：新调用日志已落库，旧聚合结果不再准确
        invalidate_summary_cache()
