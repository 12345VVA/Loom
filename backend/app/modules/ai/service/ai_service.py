"""
AI 模型管理服务。
"""
from __future__ import annotations

import json
import re
import time
import time as time_module
from contextlib import contextmanager
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.secret import decrypt_secret, encrypt_secret, mask_secret
from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import (
    AiAudioRequest,
    AiCatalogImportRequest,
    AiChatRequest,
    AiEmbeddingRequest,
    AiGenerationTask,
    AiImageRequest,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiResponseFormatRequest,
    AiRerankRequest,
    AiTaskSubmitRequest,
    AiVideoRequest,
    AiProvider,
)
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.adapters.base import UnsupportedCapabilityError
from app.modules.ai.service.catalog import get_catalog
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService


class AiProviderService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiProvider)

    def _before_add(self, data: dict) -> dict:
        self._ensure_unique_code(data.get("code"))
        _validate_json_config(data.get("extra_config"), "extraConfig", expected_type=dict)
        api_key = data.pop("api_key", None)
        if api_key:
            data["api_key_cipher"] = encrypt_secret(api_key)
            data["api_key_mask"] = mask_secret(api_key)
        return data

    def _before_update(self, data: dict, entity: AiProvider) -> dict:
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        _validate_json_config(data.get("extra_config"), "extraConfig", expected_type=dict)
        data.pop("api_key_cipher", None)
        data.pop("api_key_mask", None)
        api_key = data.pop("api_key", None)
        if api_key:
            data["api_key_cipher"] = encrypt_secret(api_key)
            data["api_key_mask"] = mask_secret(api_key)
        return data

    def add(self, payload: Any) -> dict:
        entity = super().add(payload)
        return self._with_secret_flags(self._finalize_data(entity.model_dump()))

    def update(self, payload: Any) -> dict:
        entity = super().update(payload)
        return self._with_secret_flags(self._finalize_data(entity.model_dump()))

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> Any:
        return self._with_secret_flags(super().info(id, current_user, relations))

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        return [self._with_secret_flags(item) for item in super().list(query, current_user, relations, is_tree, parent_field)]

    def page(self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = [self._with_secret_flags(item) for item in result.items]
        return result

    def test(self, id: int) -> dict:
        provider = self.session.get(AiProvider, id)
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="厂商不存在")
        adapter = build_adapter(provider)
        try:
            result = adapter.test()
            return {**adapter.capability_status(), **result}
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
                provider.delete_time = None
                provider.is_active = True
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
                exists.delete_time = None
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
        _validate_json_config(data.get("default_config"), "defaultConfig", expected_type=dict)
        return data

    def _before_update(self, data: dict, entity: AiModel) -> dict:
        self._ensure_provider(data.get("provider_id"))
        self._ensure_unique_model(data.get("provider_id"), data.get("code"), data.get("model_type"), exclude_id=entity.id)
        _validate_json_config(data.get("default_config"), "defaultConfig", expected_type=dict)
        return data

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        return [self._decorate(item) for item in super().list(query, current_user, relations, is_tree, parent_field)]

    def page(self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._decorate(super().info(id, current_user, relations))

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
        _validate_json_config(data.get("response_format"), "responseFormat")
        if "response_format" in data:
            data["response_format"] = _dump_response_format(data.get("response_format"))
        _validate_json_config(data.get("tools_config"), "toolsConfig")
        if data.get("is_default"):
            self._clear_default(data.get("model_id"), data.get("scenario"))
        return data

    def _before_update(self, data: dict, entity: AiModelProfile) -> dict:
        self._ensure_model(data.get("model_id"))
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        _validate_json_config(data.get("response_format"), "responseFormat")
        if "response_format" in data:
            data["response_format"] = _dump_response_format(data.get("response_format"))
        _validate_json_config(data.get("tools_config"), "toolsConfig")
        if data.get("is_default"):
            self._clear_default(data.get("model_id"), data.get("scenario"), exclude_id=entity.id)
        return data

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        query = self._profile_query(query)
        return [self._decorate(item) for item in super().list(query, current_user, relations, is_tree, parent_field)]

    def page(self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> PageResult[dict]:
        query = self._profile_query(query)
        result = super().page(query, current_user, relations)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._decorate(super().info(id, current_user, relations))

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

    def _profile_query(self, query: CrudQuery | None) -> CrudQuery | None:
        model_type = (query.raw_params.get("modelType") or query.raw_params.get("model_type")) if query else None
        if not model_type:
            return query
        model_ids = [
            item
            for item in self.session.exec(
                select(AiModel.id).where(
                    AiModel.model_type == model_type,
                    AiModel.delete_time == None,  # noqa: E711
                )
            ).all()
            if item is not None
        ]
        eq_filters = dict(query.eq_filters)
        eq_filters["model_id"] = model_ids or [-1]
        return CrudQuery(
            page=query.page,
            size=query.size,
            keyword=query.keyword,
            order=query.order,
            sort=query.sort,
            keyword_fields=query.keyword_fields,
            order_fields=query.order_fields,
            select_fields=query.select_fields,
            add_order_by=query.add_order_by,
            where_handler=query.where_handler,
            eq_filters=eq_filters,
            like_filters=query.like_filters,
            raw_params=query.raw_params,
        )


class AiModelCallLogService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiModelCallLog)

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        return [self._decorate(item) for item in super().list(query, current_user, relations, is_tree, parent_field)]

    def page(self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._decorate(super().info(id, current_user, relations))

    def _decorate(self, data: dict) -> dict:
        provider = self.session.get(AiProvider, data.get("providerId") or data.get("provider_id")) if data.get("providerId") or data.get("provider_id") else None
        model = self.session.get(AiModel, data.get("modelId") or data.get("model_id")) if data.get("modelId") or data.get("model_id") else None
        profile = self.session.get(AiModelProfile, data.get("profileId") or data.get("profile_id")) if data.get("profileId") or data.get("profile_id") else None
        data["providerName"] = provider.name if provider else None
        data["modelName"] = model.name if model else None
        data["profileName"] = profile.name if profile else None
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


class AiModelRuntimeService:
    def __init__(self, session: Session):
        self.session = session

    def chat(self, payload: AiChatRequest) -> dict:
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        return self._invoke(
            resolved,
            "chat",
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
            messages=[item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages],
            options=options,
        )

    def stream_chat(self, payload: AiChatRequest) -> Iterable[str]:
        resolved, options, response_format_overridden = self._resolve_chat(payload)
        messages = [item.model_dump() if hasattr(item, "model_dump") else item for item in payload.messages]
        return self._stream_invoke(
            resolved,
            messages=messages,
            options=options,
            request_options=payload.options,
            structured_response=options.get("response_format"),
            response_format_overridden=response_format_overridden,
        )

    def embedding(self, payload: AiEmbeddingRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="embedding", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "embedding", request_options=payload.options, input=payload.input, options=options)

    def image(self, payload: AiImageRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="image", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "image", request_options=payload.options, prompt=payload.prompt, options=options)

    def rerank(self, payload: AiRerankRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="rerank", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "rerank", request_options=payload.options, query=payload.query, documents=payload.documents, options=options)

    def audio(self, payload: AiAudioRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="audio", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "audio", request_options=payload.options, input=payload.input, options=options)

    def video(self, payload: AiVideoRequest) -> dict:
        resolved = AiModelRegistryService(self.session).resolve(model_type="video", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        return self._invoke(resolved, "video", request_options=payload.options, prompt=payload.prompt, options=options)

    def _invoke(
        self,
        resolved: dict,
        method: str,
        request_options: dict[str, Any] | None = None,
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
        **kwargs: Any,
    ) -> dict:
        provider: AiProvider = resolved["provider"]
        model: AiModel = resolved["model"]
        profile: AiModelProfile = resolved["profile"]
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        request_options = request_options or {}
        try:
            adapter = build_adapter(provider)
            result = self._invoke_with_retry(adapter, method, profile, model.code, kwargs)
            usage = result.get("usage") or {}
            self._log_call(provider, model, profile, "success", start, usage, request_id=result.get("requestId"))
            if method == "chat" and _is_structured_response(structured_response):
                result = _with_parsed_content(result)
            return {"success": True, "provider": provider.code, "model": model.code, "profile": profile.code, **result}
        except UnsupportedCapabilityError as exc:
            self._log_call(provider, model, profile, "unsupported", start, usage, str(exc))
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except Exception as exc:
            self._log_call(provider, model, profile, "error", start, usage, str(exc))
            fallback = self._fallback(profile, method, kwargs, request_options, structured_response, response_format_overridden)
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"模型调用失败: {exc}") from exc

    def _invoke_with_retry(self, adapter, method: str, profile: AiModelProfile, model_code: str, kwargs: dict[str, Any]) -> dict:
        attempts = max(0, int(profile.retry_count or 0)) + 1
        retry_delay = max(0, int(profile.retry_delay_seconds or 0))
        last_exc: Exception | None = None
        for index in range(attempts):
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["options"] = _options_without_governance(call_kwargs.get("options") or {})
                with _adapter_timeout(adapter, profile.timeout):
                    return getattr(adapter, method)(model=model_code, **call_kwargs)
            except UnsupportedCapabilityError:
                raise
            except Exception as exc:
                last_exc = exc
                if index >= attempts - 1:
                    break
                if retry_delay:
                    time_module.sleep(retry_delay)
        raise last_exc or RuntimeError("模型调用失败")

    def _resolve_chat(self, payload: AiChatRequest) -> tuple[dict, dict[str, Any], bool]:
        resolved = AiModelRegistryService(self.session).resolve(model_type="chat", scenario=payload.scenario, profile_code=payload.profile_code)
        options = {**resolved["options"], **payload.options}
        response_format_overridden = payload.response_format is not None
        request_response_format = normalize_response_format(payload.response_format) if payload.response_format else None
        if request_response_format:
            options["response_format"] = request_response_format
        elif response_format_overridden:
            options.pop("response_format", None)
        return resolved, options, response_format_overridden

    def _stream_invoke(
        self,
        resolved: dict,
        *,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        request_options: dict[str, Any] | None = None,
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
    ) -> Iterable[str]:
        provider: AiProvider = resolved["provider"]
        model: AiModel = resolved["model"]
        profile: AiModelProfile = resolved["profile"]
        start = time.perf_counter()
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        request_id: str | None = None
        emitted_delta = False
        done_sent = False
        request_options = request_options or {}

        yield _sse_event({"event": "start", "provider": provider.code, "model": model.code, "profile": profile.code})
        try:
            adapter = build_adapter(provider)
            with _adapter_timeout(adapter, profile.timeout):
                stream_events = adapter.stream_chat(model=model.code, messages=messages, options=_options_without_governance(options))
                for event in stream_events:
                    request_id = event.get("requestId") or request_id
                    usage = event.get("usage") or usage
                    event_name = event.get("event")
                    if event_name in {"delta", "thinking_delta", "tool_delta"}:
                        text = event.get("content") or ""
                        if event_name == "delta":
                            content_parts.append(text)
                            emitted_delta = True
                        yield _sse_event({"event": event_name, "content": text})
                        continue
                    if event_name == "error":
                        message = event.get("content") or "模型流式调用失败"
                        self._log_call(provider, model, profile, "error", start, usage, str(message), request_id=request_id)
                        yield _sse_event({"event": "error", "message": str(message), "status": 400})
                        return
                    if event_name == "done":
                        if event.get("usage"):
                            usage = event.get("usage") or usage
                        if event.get("requestId"):
                            request_id = event.get("requestId")
            content = "".join(content_parts)
            done_payload = {"event": "done", "content": content, "usage": usage or {}}
            if _is_structured_response(structured_response):
                parsed = _parse_content(content)
                done_payload.update(parsed)
            self._log_call(provider, model, profile, "success", start, usage, request_id=request_id)
            done_sent = True
            yield _sse_event(done_payload)
        except UnsupportedCapabilityError as exc:
            self._log_call(provider, model, profile, "unsupported", start, usage, str(exc), request_id=request_id)
            yield _sse_event({"event": "error", "message": str(exc), "status": 501})
        except Exception as exc:
            if not emitted_delta:
                fallback = self._stream_fallback(
                    profile,
                    messages,
                    request_options,
                    structured_response,
                    response_format_overridden,
                )
                if fallback is not None:
                    self._log_call(provider, model, profile, "error", start, usage, str(exc), request_id=request_id)
                    yield from fallback
                    return
            if not done_sent:
                self._log_call(provider, model, profile, "error", start, usage, str(exc), request_id=request_id)
                yield _sse_event({"event": "error", "message": f"模型调用失败: {exc}", "status": 400})

    def _stream_fallback(
        self,
        profile: AiModelProfile,
        messages: list[dict[str, Any]],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
    ) -> Iterable[str] | None:
        if not profile.fallback_profile_id:
            return None
        fallback = self.session.get(AiModelProfile, profile.fallback_profile_id)
        if not fallback:
            return None
        model = self.session.get(AiModel, fallback.model_id)
        provider = self.session.get(AiProvider, model.provider_id) if model else None
        if not model or not provider or not model.is_active or not provider.is_active:
            return None
        options = {**AiModelRegistryService(self.session)._merge_options(model, fallback), **request_options}
        if structured_response:
            options["response_format"] = structured_response
        elif response_format_overridden:
            options.pop("response_format", None)
        return self._stream_invoke(
            {"provider": provider, "model": model, "profile": fallback, "options": options},
            messages=messages,
            options=options,
            request_options=request_options,
            structured_response=structured_response or options.get("response_format"),
            response_format_overridden=response_format_overridden,
        )

    def _fallback(
        self,
        profile: AiModelProfile,
        method: str,
        kwargs: dict[str, Any],
        request_options: dict[str, Any],
        structured_response: dict[str, Any] | None = None,
        response_format_overridden: bool = False,
    ) -> dict | None:
        if not profile.fallback_profile_id:
            return None
        fallback = self.session.get(AiModelProfile, profile.fallback_profile_id)
        if not fallback:
            return None
        model = self.session.get(AiModel, fallback.model_id)
        provider = self.session.get(AiProvider, model.provider_id) if model else None
        if not model or not provider or not model.is_active or not provider.is_active:
            return None
        options = {**AiModelRegistryService(self.session)._merge_options(model, fallback), **request_options}
        if structured_response:
            options["response_format"] = structured_response
        elif response_format_overridden:
            options.pop("response_format", None)
        fallback_kwargs = {**kwargs, "options": options}
        return self._invoke(
            {"provider": provider, "model": model, "profile": fallback, "options": options},
            method,
            request_options=request_options,
            structured_response=structured_response or options.get("response_format"),
            response_format_overridden=response_format_overridden,
            **fallback_kwargs,
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
        request_id: str | None = None,
    ) -> None:
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
            request_id=request_id,
        )
        self.session.add(log)
        self.session.commit()

def _validate_json_config(value: str | None, field_label: str, expected_type: type | None = None) -> None:
    if value in (None, ""):
        return
    try:
        parsed = json.loads(value)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_label} 必须是合法 JSON") from exc
    if expected_type is not None and not isinstance(parsed, expected_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_label} 必须是 JSON 对象")

def _dump_response_format(value: str | None) -> str | None:
    response_format = normalize_response_format(_loads(value))
    if not response_format:
        return None
    return json.dumps(response_format, ensure_ascii=False)

def normalize_response_format(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, AiResponseFormatRequest):
        value = value.model_dump(by_alias=True, exclude_none=True)
    elif hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(value, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat 必须是 JSON 对象")

    format_type = value.get("type") or value.get("response_format") or "text"
    if format_type == "text":
        return None
    if format_type == "json_object":
        return {"type": "json_object"}
    if format_type != "json_schema":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.type 仅支持 text、json_object、json_schema")

    json_schema = value.get("json_schema") or value.get("jsonSchema")
    if hasattr(json_schema, "model_dump"):
        json_schema = json_schema.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(json_schema, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema 必须是 JSON 对象")

    name = str(json_schema.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema.name 不能为空")
    if len(name) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema.name 仅支持字母、数字、下划线、短横线，最长 64")

    schema = json_schema.get("schema") or json_schema.get("schema_")
    if not isinstance(schema, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responseFormat.jsonSchema.schema 必须是 JSON 对象")

    normalized_schema = {
        "name": name,
        "schema": schema,
        "strict": bool(json_schema.get("strict", True)),
    }
    description = json_schema.get("description")
    if description:
        normalized_schema["description"] = str(description)
    return {"type": "json_schema", "json_schema": normalized_schema}

def _is_structured_response(response_format: dict[str, Any] | None) -> bool:
    return bool(response_format and response_format.get("type") in {"json_object", "json_schema"})

def _with_parsed_content(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, str):
        return {**result, "parsed": None, "parseError": "content 不是字符串"}
    return {**result, **_parse_content(content)}

def _parse_content(content: str) -> dict[str, Any]:
    try:
        return {"parsed": json.loads(content), "parseError": None}
    except Exception as exc:
        return {"parsed": None, "parseError": str(exc)}

def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

def _loads(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _options_without_governance(options: dict[str, Any]) -> dict[str, Any]:
    data = dict(options or {})
    data.pop("timeout", None)
    return data


@contextmanager
def _adapter_timeout(adapter, timeout: int | None):
    if timeout is None:
        yield
        return
    previous_timeout = getattr(adapter, "timeout", None)
    previous_client = getattr(adapter, "client", None)
    adapter.timeout = float(timeout)
    if previous_client is not None and hasattr(previous_client, "with_options"):
        adapter.client = previous_client.with_options(timeout=float(timeout))
    try:
        yield
    finally:
        adapter.timeout = previous_timeout
        if previous_client is not None:
            adapter.client = previous_client


class AiGenerationTaskService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiGenerationTask)

    def submit(self, payload: AiTaskSubmitRequest | dict, current_user: User | None = None) -> dict:
        if isinstance(payload, dict):
            payload = AiTaskSubmitRequest(**payload)
        self._validate_task_type(payload.task_type)
        task = AiGenerationTask(
            task_type=payload.task_type,
            scenario=payload.scenario or "default",
            profile_code=payload.profile_code,
            request_payload=json.dumps(payload.payload, ensure_ascii=False, default=str),
            status="pending",
            progress=0,
            created_by=current_user.id if current_user else None,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        try:
            async_result = execute_ai_generation_task.delay(task.id)
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = f"任务入队失败: {exc}"[:1000]
            task.finished_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=task.error_message) from exc
        task.celery_task_id = async_result.id
        self.session.add(task)
        self.session.commit()
        return {"success": True, "taskId": task.id, "celeryTaskId": async_result.id}

    def cancel(self, id: int) -> dict:
        task = self.session.get(AiGenerationTask, id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 任务不存在")
        if task.status in {"success", "failed", "cancelled"}:
            return {"success": True, "status": task.status}
        if task.celery_task_id:
            from app.celery_app import celery_app

            try:
                celery_app.control.revoke(task.celery_task_id, terminate=True)
            except Exception:
                pass
        task.status = "cancelled"
        task.progress = 100
        task.finished_at = datetime.utcnow()
        self.session.add(task)
        self.session.commit()
        return {"success": True, "status": task.status}

    def retry(self, id: int) -> dict:
        task = self.session.get(AiGenerationTask, id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 任务不存在")
        if task.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅失败或已取消任务可以重试")
        task.status = "pending"
        task.progress = 0
        task.result_payload = None
        task.error_message = None
        task.started_at = None
        task.finished_at = None
        task.retry_count += 1
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        from app.modules.ai.tasks.generation_tasks import execute_ai_generation_task

        try:
            async_result = execute_ai_generation_task.delay(task.id)
        except Exception as exc:
            task.status = "failed"
            task.progress = 100
            task.error_message = f"任务入队失败: {exc}"[:1000]
            task.finished_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=task.error_message) from exc
        task.celery_task_id = async_result.id
        self.session.add(task)
        self.session.commit()
        return {"success": True, "taskId": task.id, "celeryTaskId": async_result.id}

    def stats(self) -> dict:
        rows = self.session.exec(select(AiGenerationTask.status, AiGenerationTask.error_message)).all()
        status_counts: dict[str, int] = {}
        recent_errors: list[str] = []
        for status_value, error_message in rows:
            status_counts[status_value] = status_counts.get(status_value, 0) + 1
            if error_message:
                recent_errors.append(error_message)
        return {"statusCounts": status_counts, "recentErrors": recent_errors[-5:]}

    def _validate_task_type(self, task_type: str) -> None:
        if task_type not in {"chat", "embedding", "image", "rerank", "audio", "video"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的 AI 任务类型")


class AiModelCallStatsService:
    def __init__(self, session: Session):
        self.session = session

    def summary(self) -> dict:
        logs = list(self.session.exec(select(AiModelCallLog)).all())
        total = len(logs)
        success = len([item for item in logs if item.status == "success"])
        errors = len([item for item in logs if item.status != "success"])
        avg_latency = int(sum(item.latency_ms for item in logs) / total) if total else 0
        token_total = sum(item.total_tokens for item in logs)
        groups: dict[str, dict[str, Any]] = {}
        for item in logs:
            key = f"{item.provider_id or '-'}:{item.model_id or '-'}:{item.profile_id or '-'}"
            group = groups.setdefault(key, {
                "providerId": item.provider_id,
                "modelId": item.model_id,
                "profileId": item.profile_id,
                "total": 0,
                "success": 0,
                "error": 0,
                "totalTokens": 0,
                "avgLatencyMs": 0,
                "_latency": 0,
            })
            group["total"] += 1
            group["success" if item.status == "success" else "error"] += 1
            group["totalTokens"] += item.total_tokens
            group["_latency"] += item.latency_ms
        for group in groups.values():
            group["avgLatencyMs"] = int(group["_latency"] / group["total"]) if group["total"] else 0
            group.pop("_latency", None)
        return {
            "total": total,
            "success": success,
            "error": errors,
            "successRate": round(success / total, 4) if total else 0,
            "avgLatencyMs": avg_latency,
            "totalTokens": token_total,
            "groups": list(groups.values()),
        }
