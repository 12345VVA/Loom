"""工作流产物 CRUD 服务：读路径走自动数据权限，删除按归属校验。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact


class WorkflowArtifactService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, WorkflowArtifact)

    def page(self, query: Any, current_user: User | None = None, relations: tuple = ()) -> Any:
        result = super().page(query, current_user, relations=relations)
        self._backfill_storage_urls(result.items)
        return result

    def _backfill_storage_urls(self, items: list[dict]) -> None:
        from app.modules.media.model.media import MediaAsset

        missing_urls = [
            item.get("original_url") or item.get("originalUrl")
            for item in items
            if not (item.get("storage_url") or item.get("storageUrl"))
            and (item.get("original_url") or item.get("originalUrl"))
        ]
        if not missing_urls:
            return

        assets = list(
            self.session.exec(
                select(MediaAsset).where(
                    MediaAsset.original_url.in_(missing_urls),
                    MediaAsset.status == "success",
                    MediaAsset.delete_time == None,  # noqa: E711
                )
            ).all()
        )
        url_map = {a.original_url: a.storage_url for a in assets if a.original_url and a.storage_url}
        for item in items:
            orig = item.get("original_url") or item.get("originalUrl")
            if orig and orig in url_map:
                item["storage_url"] = url_map[orig]
                item["storageUrl"] = url_map[orig]

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前校验归属：BaseAdminCrudService.delete 不走 DataScope，需显式拦截（防 IDOR）。"""
        if current_user is not None and ids and not current_user.is_super_admin:
            rows = list(self.session.exec(select(WorkflowArtifact).where(WorkflowArtifact.id.in_(ids))).all())
            for row in rows:
                if row.user_id is not None and row.user_id != current_user.id:
                    raise HTTPException(status_code=403, detail="无权删除他人产物")
        return super().delete(ids, payload=payload, soft_delete=soft_delete)
