"""AI 模型调用日志服务。"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import AiModel, AiModelCallLog, AiModelProfile, AiProvider
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService


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

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = [self._decorate(item) for item in result.items]
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._decorate(super().info(id, current_user, relations))

    def _decorate(self, data: dict) -> dict:
        provider = (
            self.session.get(AiProvider, data.get("providerId") or data.get("provider_id"))
            if data.get("providerId") or data.get("provider_id")
            else None
        )
        model = (
            self.session.get(AiModel, data.get("modelId") or data.get("model_id"))
            if data.get("modelId") or data.get("model_id")
            else None
        )
        profile = (
            self.session.get(AiModelProfile, data.get("profileId") or data.get("profile_id"))
            if data.get("profileId") or data.get("profile_id")
            else None
        )
        user = (
            self.session.get(User, data.get("userId") or data.get("user_id"))
            if data.get("userId") or data.get("user_id")
            else None
        )
        data["providerName"] = provider.name if provider else None
        data["modelName"] = model.name if model else None
        data["profileName"] = profile.name if profile else None
        data["username"] = user.username if user else None
        data["costUsd"] = round((data.get("costMicroUsd") or data.get("cost_micro_usd") or 0) / 1_000_000, 6)
        return data
