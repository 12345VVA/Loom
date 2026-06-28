"""AI 模型调用配置解析服务。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.ai.service.utils import _loads, normalize_response_format


class AiModelRegistryService:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, *, model_type: str, scenario: str = "default", profile_code: str | None = None) -> dict:
        if profile_code:
            profile = self.session.exec(
                select(AiModelProfile).where(AiModelProfile.code == profile_code, AiModelProfile.is_active == True)  # noqa: E712
            ).first()
        else:
            profile = self.session.exec(
                select(AiModelProfile)
                .join(AiModel, AiModel.id == AiModelProfile.model_id)
                .where(
                    AiModelProfile.scenario == scenario,
                    AiModelProfile.is_default == True,  # noqa: E712
                    AiModelProfile.is_active == True,  # noqa: E712
                    AiModel.model_type == model_type,
                    AiModel.is_active == True,  # noqa: E712
                )
                .order_by(AiModelProfile.sort_order.desc(), AiModelProfile.created_at.desc())
            ).first()
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可用的模型调用配置")
        model = self.session.get(AiModel, profile.model_id)
        if not model or not model.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型不存在或已禁用")
        provider = self.session.get(AiProvider, model.provider_id)
        if not provider or not provider.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型厂商不存在或已禁用")
        if model.model_type != model_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调用配置模型类型不匹配")
        return {
            "profile": profile,
            "model": model,
            "provider": provider,
            "options": self._merge_options(model, profile),
        }

    def _merge_options(self, model: AiModel, profile: AiModelProfile) -> dict:
        options = _loads(model.default_config)
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
