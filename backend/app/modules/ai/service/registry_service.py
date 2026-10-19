"""AI 模型调用配置解析服务。"""

from __future__ import annotations

from typing import TypeVar

from sqlmodel import Session, select

from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.ai.service.errors import AiInvocationError
from app.modules.ai.service.utils import _loads, normalize_response_format

_EntityT = TypeVar("_EntityT")


def live_record(obj: _EntityT | None) -> _EntityT | None:
    """软删除不变量（AI-001）：delete_time 非空即已删除，运行时解析一律视同不存在。

    session.get() 与手写 select 都不会自动过滤软删行，所有运行时解析路径
    （resolve / _fallback / _stream_fallback）必须经由本 helper 判定，防止
    后台"删除"的配置仍被调用并计费。
    """
    if obj is None or getattr(obj, "delete_time", None) is not None:
        return None
    return obj


class AiModelRegistryService:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, *, model_type: str, scenario: str = "default", profile_code: str | None = None) -> dict:
        if profile_code:
            profile = self.session.exec(
                select(AiModelProfile).where(
                    AiModelProfile.code == profile_code,
                    AiModelProfile.is_active == True,  # noqa: E712
                    AiModelProfile.delete_time == None,  # noqa: E711
                )
            ).first()
        else:
            profile = self.session.exec(
                select(AiModelProfile)
                .join(AiModel, AiModel.id == AiModelProfile.model_id)
                .where(
                    AiModelProfile.scenario == scenario,
                    AiModelProfile.is_default == True,  # noqa: E712
                    AiModelProfile.is_active == True,  # noqa: E712
                    AiModelProfile.delete_time == None,  # noqa: E711
                    AiModel.model_type == model_type,
                    AiModel.is_active == True,  # noqa: E712
                    AiModel.delete_time == None,  # noqa: E711
                )
                .order_by(AiModelProfile.sort_order.desc(), AiModelProfile.created_at.desc())
            ).first()
        if not profile:
            raise AiInvocationError("未找到可用的模型调用配置", status_code=404)
        model = live_record(self.session.get(AiModel, profile.model_id))
        if not model or not model.is_active:
            raise AiInvocationError("模型不存在或已禁用", status_code=400)
        provider = live_record(self.session.get(AiProvider, model.provider_id))
        if not provider or not provider.is_active:
            raise AiInvocationError("模型厂商不存在或已禁用", status_code=400)
        if model.model_type != model_type:
            raise AiInvocationError("调用配置模型类型不匹配", status_code=400)
        return {
            "profile": profile,
            "model": model,
            "provider": provider,
            "options": self._merge_options(model, profile),
        }

    def _merge_options(self, model: AiModel, profile: AiModelProfile) -> dict:
        options = _loads(model.default_config)
        if profile.custom_config:
            custom = _loads(profile.custom_config)
            if isinstance(custom, dict):
                options.update(custom)
        if profile.temperature is not None:
            options["temperature"] = profile.temperature
        if profile.top_p is not None:
            options["top_p"] = profile.top_p
        if profile.max_tokens is not None:
            options["max_tokens"] = profile.max_tokens
        if profile.timeout is not None:
            options["timeout"] = profile.timeout
        if profile.response_format:
            response_format = normalize_response_format(_loads(profile.response_format))
            if response_format:
                options["response_format"] = response_format
        if profile.tools_config:
            tools = _loads(profile.tools_config)
            if tools:
                options["tools"] = tools
        return options
