"""fallback 降级链：运行期防环 + sync/stream 双路径降级（AI-013 拆分，纯搬迁）。"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlmodel import Session

from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.ai.service.registry_service import AiModelRegistryService, live_record
from app.modules.ai.service.runtime.common import MAX_FALLBACK_DEPTH, _fallback_depth
from app.modules.ai.service.utils import sanitize_options_for_log
from app.modules.base.model.auth import User

logger = logging.getLogger(__name__)


class FallbackMixin:
    def _fallback_chain_has_cycle(self, profile: AiModelProfile, session: Session) -> bool:
        """运行期同步检测 fallback 链是否存在环或超过最大深度。

        不依赖 contextvar，对流式生成器的惰性求值同样可靠，作为保存期环校验的运行期兜底
        （堵住 TOCTOU 并发或直接改库形成的环）。返回 True 时调用方应停止降级。
        """
        visited: set[int] = set()
        cursor = profile
        depth = 0
        while cursor is not None and cursor.fallback_profile_id and depth < MAX_FALLBACK_DEPTH:
            if cursor.id in visited:
                return True
            visited.add(cursor.id)
            nxt = session.get(AiModelProfile, cursor.fallback_profile_id)
            if nxt is None:
                return False
            cursor = nxt
            depth += 1
        return cursor is not None and cursor.fallback_profile_id is not None

    def _stream_fallback(
        self,
        profile: AiModelProfile,
        messages: list[dict[str, Any]],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
        *,
        session: Session,
    ) -> Iterable[str] | None:
        if not profile.fallback_profile_id:
            return None
        # 运行期同步防环（不依赖 contextvar 的生成器时序，流式路径可靠）：堵住并发/脏数据成环导致的无限递归
        if self._fallback_chain_has_cycle(profile, session):
            logger.warning("AI 流式 fallback 链检测到环或超深，停止降级")
            return None
        # 深度兜底：fallback 链过长时停止降级
        depth = _fallback_depth.get()
        if depth >= MAX_FALLBACK_DEPTH:
            logger.warning("AI 流式 fallback 链已达最大深度 %d，停止降级", MAX_FALLBACK_DEPTH)
            return None
        token = _fallback_depth.set(depth + 1)
        try:
            fallback = session.get(AiModelProfile, profile.fallback_profile_id)
            if not fallback or fallback.delete_time is not None:
                return None
            model = live_record(session.get(AiModel, fallback.model_id))
            provider = live_record(session.get(AiProvider, model.provider_id)) if model else None
            if not model or not provider or not model.is_active or not provider.is_active:
                return None
            options = {**AiModelRegistryService(session)._merge_options(model, fallback), **request_options}
            if structured_response:
                options["response_format"] = structured_response
            elif response_format_overridden:
                options.pop("response_format", None)
            return self._stream_invoke(
                {"provider": provider, "model": model, "profile": fallback, "options": options},
                current_user=current_user,
                messages=messages,
                options=options,
                request_options=request_options,
                structured_response=structured_response or options.get("response_format"),
                response_format_overridden=response_format_overridden,
            )
        finally:
            _fallback_depth.reset(token)

    def _fallback(
        self,
        profile: AiModelProfile,
        method: str,
        kwargs: dict[str, Any],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        current_user: User | None = None,
        task_id: int | None = None,
    ) -> dict | None:
        if not profile.fallback_profile_id:
            return None
        # 运行期同步防环（不依赖 contextvar）：堵住并发/脏数据成环导致的无限递归
        if self._fallback_chain_has_cycle(profile, self.session):
            logger.warning("AI fallback 链检测到环或超深，停止降级")
            return None
        # 深度兜底：fallback 链过长时停止降级
        depth = _fallback_depth.get()
        if depth >= MAX_FALLBACK_DEPTH:
            logger.warning("AI fallback 链已达最大深度 %d，停止降级", MAX_FALLBACK_DEPTH)
            return None
        token = _fallback_depth.set(depth + 1)
        try:
            fallback = self.session.get(AiModelProfile, profile.fallback_profile_id)
            if not fallback or fallback.delete_time is not None:
                return None
            model = live_record(self.session.get(AiModel, fallback.model_id))
            provider = live_record(self.session.get(AiProvider, model.provider_id)) if model else None
            if not model or not provider or not model.is_active or not provider.is_active:
                return None
            options = {**AiModelRegistryService(self.session)._merge_options(model, fallback), **request_options}
            if structured_response:
                options["response_format"] = structured_response
            elif response_format_overridden:
                options.pop("response_format", None)
            if method == "image":
                logger.warning(
                    "AI 生图触发兜底模型",
                    extra={
                        "method": method,
                        "from_profile": profile.code,
                        "to_profile": fallback.code,
                        "to_provider": provider.code,
                        "to_model": model.code,
                        "options": sanitize_options_for_log(options),
                    },
                )
            fallback_kwargs = {**kwargs, "options": options}
            return self._invoke(
                {"provider": provider, "model": model, "profile": fallback, "options": options},
                method,
                current_user=current_user,
                task_id=task_id,
                request_options=request_options,
                structured_response=structured_response or options.get("response_format"),
                response_format_overridden=response_format_overridden,
                **fallback_kwargs,
            )
        finally:
            _fallback_depth.reset(token)
