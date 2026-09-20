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
