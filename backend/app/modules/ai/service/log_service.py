"""AI 模型调用日志服务。"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import AiModel, AiModelCallLog, AiModelProfile, AiProvider
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService


def _collect_ids(items: list[dict], camel: str, snake: str) -> set:
    ids: set = set()
    for d in items:
        value = d.get(camel)
        if value is None:
            value = d.get(snake)
        if value is not None:
            ids.add(value)
    return ids


def _bulk_attr_map(session: Session, model: Any, ids: set, attr: str) -> dict:
    if not ids:
        return {}
    rows = session.exec(select(model).where(model.id.in_(ids))).all()
    return {row.id: getattr(row, attr) for row in rows}


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
        return self._batch_decorate(list(super().list(query, current_user, relations, is_tree, parent_field)))

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = self._batch_decorate(list(result.items))
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._batch_decorate([super().info(id, current_user, relations)])[0]

    def _batch_decorate(self, items: list[dict]) -> list[dict]:
        provider_map = _bulk_attr_map(
            self.session, AiProvider, _collect_ids(items, "providerId", "provider_id"), "name"
        )
        model_map = _bulk_attr_map(self.session, AiModel, _collect_ids(items, "modelId", "model_id"), "name")
        profile_map = _bulk_attr_map(
            self.session, AiModelProfile, _collect_ids(items, "profileId", "profile_id"), "name"
        )
        user_map = _bulk_attr_map(self.session, User, _collect_ids(items, "userId", "user_id"), "username")

        for data in items:
            pid = data.get("providerId") if data.get("providerId") is not None else data.get("provider_id")
            mid = data.get("modelId") if data.get("modelId") is not None else data.get("model_id")
            pfid = data.get("profileId") if data.get("profileId") is not None else data.get("profile_id")
            uid = data.get("userId") if data.get("userId") is not None else data.get("user_id")

            data["providerName"] = provider_map.get(pid)
            data["modelName"] = model_map.get(mid)
            data["profileName"] = profile_map.get(pfid)
            data["username"] = user_map.get(uid)
            data["costUsd"] = round((data.get("costMicroUsd") or data.get("cost_micro_usd") or 0) / 1_000_000, 6)

        return items
