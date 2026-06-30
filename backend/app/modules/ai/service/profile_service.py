"""AI 模型调用配置服务。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import (
    AiChatRequest,
    AiEmbeddingRequest,
    AiImageRequest,
    AiModel,
    AiModelProfile,
    AiProvider,
)
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.ai.service.utils import _dump_response_format, _validate_json_config
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService


class AiModelProfileService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiModelProfile)

    def _before_add(self, data: dict) -> dict:
        self._ensure_model(data.get("model_id"))
        self._ensure_unique_code(data.get("code"))
        self._ensure_fallback_acyclic(None, data.get("fallback_profile_id"))
        _validate_json_config(data.get("response_format"), "responseFormat")
        if "response_format" in data:
            data["response_format"] = _dump_response_format(data.get("response_format"))
        _validate_json_config(data.get("tools_config"), "toolsConfig")
        if data.get("is_default"):
            self._clear_default(data.get("model_id"), data.get("scenario"))
        return data

    def _before_update(self, data: dict, entity: AiModelProfile) -> dict:
        # 部分更新：仅当显式传了 model_id 才校验模型存在（_ensure_model 对 None 会报错）
        if data.get("model_id") is not None:
            self._ensure_model(data.get("model_id"))
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        if "fallback_profile_id" in data:
            self._ensure_fallback_acyclic(entity.id, data.get("fallback_profile_id"))
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

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
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
            return AiModelRuntimeService(self.session).embedding(
                AiEmbeddingRequest(profile_code=profile.code, input=prompt)
            )
        if model and model.model_type == "image":
            return AiModelRuntimeService(self.session).image(AiImageRequest(profile_code=profile.code, prompt=prompt))
        return AiModelRuntimeService(self.session).chat(
            AiChatRequest(profile_code=profile.code, messages=[{"role": "user", "content": prompt}])
        )

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

    def _ensure_fallback_acyclic(self, profile_id: int | None, fallback_id: int | None) -> None:
        """校验兜底 Profile 链：目标存在且启用，且不存在环（防止运行期 _fallback 无限递归）。"""
        if not fallback_id:
            return
        target = self.session.get(AiModelProfile, fallback_id)
        if not target:
            raise HTTPException(status_code=400, detail="兜底模型 Profile 不存在")
        if not target.is_active:
            raise HTTPException(status_code=400, detail="兜底模型 Profile 已禁用，无法作为降级目标")
        # 沿 fallback 链向下遍历，检测环与自指（visited 含自身 id 防止 A→A）
        visited: set[int] = {profile_id} if profile_id is not None else set()
        cursor = target
        depth = 0
        while cursor is not None and cursor.fallback_profile_id and depth < 16:
            nxt = cursor.fallback_profile_id
            if nxt == cursor.id or nxt in visited:
                raise HTTPException(status_code=400, detail="兜底模型 Profile 链存在环，无法保存")
            visited.add(cursor.id)
            cursor = self.session.get(AiModelProfile, nxt)
            depth += 1

    def _decorate(self, data: dict) -> dict:
        model = self.session.get(AiModel, data.get("modelId") or data.get("model_id"))
        provider = self.session.get(AiProvider, model.provider_id) if model else None
        data["modelName"] = model.name if model else None
        data["modelType"] = model.model_type if model else None
        data["modelCode"] = model.code if model else None
        data["modelCapabilities"] = model.capabilities if model else None
        data["providerName"] = provider.name if provider else None
        data["providerCode"] = provider.code if provider else None
        data["providerAdapter"] = provider.adapter if provider else None
        data["modelDefaultConfig"] = model.default_config if model else None
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
