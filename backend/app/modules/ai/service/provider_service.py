"""AI 厂商管理服务。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.secret import encrypt_secret, mask_secret
from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import AiCatalogImportRequest, AiModel, AiProvider
from app.modules.ai.service.adapters import build_adapter
from app.modules.ai.service.catalog import get_catalog
from app.modules.ai.service.utils import _validate_json_config
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
        return [
            self._with_secret_flags(item)
            for item in super().list(query, current_user, relations, is_tree, parent_field)
        ]

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
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

    def sync_models(self, id: int) -> dict:
        provider = self.session.get(AiProvider, id)
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="厂商不存在")
        try:
            models = build_adapter(provider).list_models()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"同步模型失败: {exc}") from exc
        created = 0
        existing_count = 0
        for item in models:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            exists = self.session.exec(
                select(AiModel).where(AiModel.provider_id == provider.id, AiModel.code == code)
            ).first()
            if exists:
                existing_count += 1
                exists.name = str(item.get("name") or code)
                exists.delete_time = None
                exists.is_active = False
                self.session.add(exists)
                continue
            self.session.add(
                AiModel(
                    provider_id=provider.id,
                    code=code,
                    name=str(item.get("name") or code),
                    model_type="chat",
                    capabilities="sync-pending,manual-classification-required",
                    is_active=False,
                )
            )
            created += 1
        self.session.commit()
        return {"success": True, "created": created, "updated": existing_count, "total": len(models)}

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
                    exists = AiModel(
                        provider_id=provider.id,
                        code=model_item["code"],
                        name=model_item["name"],
                        model_type=model_item.get("model_type", "chat"),
                    )
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
