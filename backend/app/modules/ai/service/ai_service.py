"""
AI 模型管理服务。
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.secret import decrypt_secret, encrypt_secret, mask_secret
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiCatalogImportRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiImageRequest,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiRerankRequest,
    AiVideoRequest,
    AiProvider,
)
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.catalog import get_catalog
from app.modules.base.service.admin_service import BaseAdminCrudService


class AiProviderService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiProvider)

    def _before_add(self, data: dict) -> dict:
        self._ensure_unique_code(data.get("code"))
        api_key = data.pop("api_key", None)
        if api_key:
            data["api_key_cipher"] = encrypt_secret(api_key)
            data["api_key_mask"] = mask_secret(api_key)
        return data

    def _before_update(self, data: dict, entity: AiProvider) -> dict:
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        api_key = data.pop("api_key", None)
        if api_key:
            data["api_key_cipher"] = encrypt_secret(api_key)
            data["api_key_mask"] = mask_secret(api_key)
        data.pop("api_key_cipher", None)
        data.pop("api_key_mask", None)
        return data

    def add(self, payload: Any) -> dict:
        entity = super().add(payload)
        return self._with_secret_flags(self._finalize_data(entity.model_dump()))

    def update(self, payload: Any) -> dict:
        entity = super().update(payload)
        return self._with_secret_flags(self._finalize_data(entity.model_dump()))

    def info(self, *args, **kwargs) -> Any:
        return self._with_secret_flags(super().info(*args, **kwargs))

    def list(self, *args, **kwargs) -> list[dict]:
        return [self._with_secret_flags(item) for item in super().list(*args, **kwargs)]

    def page(self, *args, **kwargs):
        result = super().page(*args, **kwargs)
        result.items = [self._with_secret_flags(item) for item in result.items]
        return result

    def test(self, id: int) -> dict:
        provider = self.session.get(AiProvider, id)
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="厂商不存在")
        adapter = build_adapter(provider)
        try:
            return adapter.test()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"连接测试失败: {exc}") from exc

    def catalog(self) -> list[dict]:
        return get_catalog()

    def import_catalog(self, payload: AiCatalogImportRequest) -> dict:
        items = get_catalog(payload.provider_code)
        if not items:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预设厂商不存在")
        imported_providers = 0
        imported_models = 0
        for item in items:
            provider = self.session.exec(select(AiProvider).where(AiProvider.code == item["code"])).first()
            if provider is None:
                provider = AiProvider(
                    code=item["code"],
                    name=item["name"],
                    adapter=item["adapter"],
                    base_url=item.get("base_url"),
                    is_active=True,
                )
                self.session.add(provider)
                self.session.commit()
                self.session.refresh(provider)
                imported_providers += 1
            else:
                provider.name = item["name"]
                provider.adapter = item["adapter"]
                provider.base_url = item.get("base_url") or provider.base_url
                self.session.add(provider)
                self.session.commit()

            for model_item in item.get("models", []):
                exists = self.session.exec(
                    select(AiModel).where(
                        AiModel.provider_id == provider.id,
                        AiModel.code == model_item["code"],
                        AiModel.model_type == model_item.get("model_type", "chat"),
                    )
                ).first()
                if exists and not payload.overwrite_models:
                    continue
                if exists is None:
                    exists = AiModel(provider_id=provider.id, code=model_item["code"], name=model_item["name"], model_type=model_item.get("model_type", "chat"))
                    imported_models += 1
                exists.name = model_item["name"]
                exists.capabilities = model_item.get("capabilities")
                exists.context_window = model_item.get("context_window")
                exists.max_output_tokens = model_item.get("max_output_tokens")
                exists.is_active = True
                self.session.add(exists)
            self.session.commit()
        return {"success": True, "providers": imported_providers, "models": imported_models}

    def _ensure_unique_code(self, code: str | None, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(AiProvider).where(AiProvider.code == code)
        if exclude_id is not None:
            statement = statement.where(AiProvider.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="厂商编码已存在")

    def _with_secret_flags(self, data: dict) -> dict:
        data.pop("apiKeyCipher", None)
        data.pop("api_key_cipher", None)
        data["hasApiKey"] = bool(data.get("apiKeyMask") or data.get("api_key_mask"))
        return data


class AiModelService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiModel)

    def _before_add(self, data: dict) -> dict:
        self._ensure_provider(data.get("provider_id"))
        self._ensure_unique_model(data.get("provider_id"), data.get("code"), data.get("model_type"))
        return data

    def _before_update(self, data: dict, entity: AiModel) -> dict:
        self._ensure_provider(data.get("provider_id"))
        self._ensure_unique_model(data.get("provider_id"), data.get("code"), data.get("model_type"), exclude_id=entity.id)
        return data

    def list(self, *args, **kwargs) -> list[dict]:
        return [self._decorate(item) for item in super().list(*args, **kwargs)]

    def page(self, *args, **kwargs):
        result = super().page(*args, **kwargs)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, *args, **kwargs) -> dict:
        return self._decorate(super().info(*args, **kwargs))

    def _ensure_provider(self, provider_id: int | None) -> None:
        if provider_id is None or not self.session.get(AiProvider, provider_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="厂商不存在")

    def _ensure_unique_model(self, provider_id: int | None, code: str | None, model_type: str | None, exclude_id: int | None = None) -> None:
        if provider_id is None or not code or not model_type:
            return
        statement = select(AiModel).where(AiModel.provider_id == provider_id, AiModel.code == code, AiModel.model_type == model_type)
        if exclude_id is not None:
            statement = statement.where(AiModel.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同厂商同类型模型编码已存在")

    def _decorate(self, data: dict) -> dict:
        provider = self.session.get(AiProvider, data.get("providerId") or data.get("provider_id"))
        data["providerName"] = provider.name if provider else None
        return data


class AiModelProfileService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiModelProfile)

    def _before_add(self, data: dict) -> dict:
        self._ensure_model(data.get("model_id"))
        self._ensure_unique_code(data.get("code"))
        if data.get("is_default"):
            self._clear_default(data.get("model_id"), data.get("scenario"))
        return data

    def _before_update(self, data: dict, entity: AiModelProfile) -> dict:
        self._ensure_model(data.get("model_id"))
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        if data.get("is_default"):
            self._clear_default(data.get("model_id"), data.get("scenario"), exclude_id=entity.id)
        return data

    def list(self, *args, **kwargs) -> list[dict]:
        return [self._decorate(item) for item in super().list(*args, **kwargs)]

    def page(self, *args, **kwargs):
        result = super().page(*args, **kwargs)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, *args, **kwargs) -> dict:
        return self._decorate(super().info(*args, **kwargs))

    def set_default(self, id: int) -> dict:
        profile = self.session.get(AiModelProfile, id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调用配置不存在")
        self._clear_default(profile.model_id, profile.scenario, exclude_id=profile.id)
        profile.is_default = True
        profile.is_active = True
        self.session.add(profile)
        self.session.commit()
        return {"success": True}

    def test(self, id: int, prompt: str) -> dict:
        profile = self.session.get(AiModelProfile, id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调用配置不存在")
        model = self.session.get(AiModel, profile.model_id)
        if model and model.model_type == "embedding":
            return AiModelRuntimeService(self.session).embedding(AiEmbeddingRequest(profile_code=profile.code, input=prompt))
        if model and model.model_type == "image":
            return AiModelRuntimeService(self.session).image(AiImageRequest(profile_code=profile.code, prompt=prompt))
        return AiModelRuntimeService(self.session).chat(AiChatRequest(profile_code=profile.code, messages=[{"role": "user", "content": prompt}]))

    def _ensure_model(self, model_id: int | None) -> None:
        if model_id is None or not self.session.get(AiModel, model_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型不存在")

    def _ensure_unique_code(self, code: str | None, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(AiModelProfile).where(AiModelProfile.code == code)
        if exclude_id is not None:
            statement = statement.where(AiModelProfile.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="配置编码已存在")

    def _clear_default(self, model_id: int | None, scenario: str | None, exclude_id: int | None = None) -> None:
        model = self.session.get(AiModel, model_id) if model_id else None
        if not model:
            return
        rows = self.session.exec(
            select(AiModelProfile)
            .join(AiModel, AiModel.id == AiModelProfile.model_id)
            .where(AiModelProfile.scenario == (scenario or "default"), AiModel.model_type == model.model_type)
        ).all()
        for row in rows:
            if exclude_id is not None and row.id == exclude_id:
                continue
            row.is_default = False
            self.session.add(row)

    def _decorate(self, data: dict) -> dict:
        model = self.session.get(AiModel, data.get("modelId") or data.get("model_id"))
        provider = self.session.get(AiProvider, model.provider_id) if model else None
        data["modelName"] = model.name if model else None
        data["modelType"] = model.model_type if model else None
        data["providerName"] = provider.name if provider else None
        return data


class AiModelRegistryService:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, *, model_type: str, scenario: str = "default", profile_code: str | None = None) -> dict:
        if profile_code:
            profile = self.session.exec(select(AiModelProfile).where(AiModelProfile.code == profile_code, AiModelProfile.is_active == True)).first()  # noqa: E712
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
        return {"profile": profile, "model": model, "provider": provider, "options": self._merge_options(model, profile)}

    def _merge_options(self, model: AiModel, profile: AiModelProfile) -> dict:
        options = _loads(model.default_config)
        if profile.temperature is not None:
            options["temperature"] = profile.temperature
        if profile.top_p is not None:
            options["top_p"] = profile.top_p
        if profile.max_tokens is not None:
            options["max_tokens"] = profile.max_tokens
        if profile.response_format:
            options["response_format"] = _loads(profile.response_format) or profile.response_format
        if profile.tools_config:
            tools = _loads(profile.tools_config)
            if tools:
                options["tools"] = tools
        return options


class AiModelRuntimeService:
    def __init__(self, session: Session):
        self.session = session

    def chat(self, payload: AiChatRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="chat", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "chat", messages=[item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages], options=options)

    def embedding(self, payload: AiEmbeddingRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="embedding", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "embedding", input=payload.input, options=options)

    def image(self, payload: AiImageRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="image", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "image", prompt=payload.prompt, options=options)

    def rerank(self, payload: AiRerankRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="rerank", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "rerank", query=payload.query, documents=payload.documents, options=options)

    def audio(self, payload: AiAudioRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="audio", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "audio", input=payload.input, options=options)

    def video(self, payload: AiVideoRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="video", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "video", prompt=payload.prompt, options=options)

    def _invoke(self, resolved: dict, method: str, **kwargs: Any) -> dict:
        provider: AiProvider = resolved["provider"]
        model: AiModel = resolved["model"]
        profile: AiModelProfile = resolved["profile"]
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        try:
            adapter = build_adapter(provider)
            result = getattr(adapter, method)(model=model.code, **kwargs)
            usage = result.get("usage") or {}
            self._log_call(provider, model, profile, "success", start, usage)
            return {"success": True, "provider": provider.code, "model": model.code, "profile": profile.code, **result}
        except UnsupportedCapabilityError as exc:
            self._log_call(provider, model, profile, "unsupported", start, usage, str(exc))
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except Exception as exc:
            self._log_call(provider, model, profile, "error", start, usage, str(exc))
            fallback = self._fallback(profile, method, kwargs)
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"模型调用失败: {exc}") from exc

    def _fallback(self, profile: AiModelProfile, method: str, kwargs: dict[str, Any]) -> dict | None:
        if not profile.fallback_profile_id:
            return None
        fallback = self.session.get(AiModelProfile, profile.fallback_profile_id)
        if not fallback:
            return None
        model = self.session.get(AiModel, fallback.model_id)
        provider = self.session.get(AiProvider, model.provider_id) if model else None
        if not model or not provider or not model.is_active or not provider.is_active:
            return None
        return self._invoke({"provider": provider, "model": model, "profile": fallback, "options": AiModelRegistryService(self.session)._merge_options(model, fallback)}, method, **kwargs)

    def _log_call(self, provider: AiProvider, model: AiModel, profile: AiModelProfile, status_value: str, start: float, usage: dict, error: str | None = None) -> None:
        log = AiModelCallLog(
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            scenario=profile.scenario,
            model_type=model.model_type,
            status=status_value,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=int(usage.get("promptTokens") or 0),
            completion_tokens=int(usage.get("completionTokens") or 0),
            total_tokens=int(usage.get("totalTokens") or 0),
            error_message=(error or "")[:500] or None,
        )
        self.session.add(log)
        self.session.commit()

def _loads(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}
