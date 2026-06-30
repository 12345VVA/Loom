"""AI 模型管理服务。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import AiModel, AiProvider
from app.modules.ai.service.utils import _validate_json_config
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService


class AiModelService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiModel)

    def _before_add(self, data: dict) -> dict:
        self._ensure_provider(data.get("provider_id"))
        self._ensure_unique_model(data.get("provider_id"), data.get("code"), data.get("model_type"))
        _validate_json_config(data.get("default_config"), "defaultConfig", expected_type=dict)
        return data

    def _before_update(self, data: dict, entity: AiModel) -> dict:
        # 部分更新：仅当显式传了 provider_id 才校验厂商存在（_ensure_provider 对 None 会报错）
        if data.get("provider_id") is not None:
            self._ensure_provider(data.get("provider_id"))
        self._ensure_unique_model(
            data.get("provider_id"), data.get("code"), data.get("model_type"), exclude_id=entity.id
        )
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

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._decorate(super().info(id, current_user, relations))

    def _ensure_provider(self, provider_id: int | None) -> None:
        if provider_id is None or not self.session.get(AiProvider, provider_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="厂商不存在")

    def _ensure_unique_model(
        self, provider_id: int | None, code: str | None, model_type: str | None, exclude_id: int | None = None
    ) -> None:
        if provider_id is None or not code or not model_type:
            return
        statement = select(AiModel).where(
            AiModel.provider_id == provider_id, AiModel.code == code, AiModel.model_type == model_type
        )
        if exclude_id is not None:
            statement = statement.where(AiModel.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同厂商同类型模型编码已存在")

    def _decorate(self, data: dict) -> dict:
        provider = self.session.get(AiProvider, data.get("providerId") or data.get("provider_id"))
        data["providerName"] = provider.name if provider else None
        return data
