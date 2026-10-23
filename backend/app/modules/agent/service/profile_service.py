"""智能体（AgentProfile）CRUD 服务：编号自动生成 / 可见性过滤 / 状态字段保护。

权限口径（设计 3.6 + 需求 Q2）：全员可建；管理面 draft 仅创建者可见（管理员全量）；
publish/rollback/delete 为「创建者或管理员」（P4 落地，本文件先承载 CRUD 骨架）。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.modules.agent.model.agent import AGENT_STATUS_DRAFT
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService


def _is_super_admin(current_user: User | None) -> bool:
    """与 asset/workflow_eval 同款防御取值。"""
    return bool(current_user is not None and getattr(current_user, "is_super_admin", False))


class AgentProfileService(BaseAdminCrudService):
    """agent_profile 活表 CRUD；draft/snapshot/publish 见 profile_service 同文件的发布段（P4）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentProfile

        super().__init__(session, model or AgentProfile)

    # --- CRUD 生命周期 ---

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增：强制 draft + 创建者；code 留空自动生成 ag-{8位base36}（照 asset 先例）。"""
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)
        data.pop("created_by", None)
        data.pop("enabled", None)  # 启停只经 toggleEnabled
        data["status"] = AGENT_STATUS_DRAFT
        if current_user is not None:
            data["created_by"] = current_user.id
        tools = data.get("tools")
        data["tools"] = json.dumps(tools, ensure_ascii=False) if tools else None
        if not str(data.get("code") or "").strip():
            data["code"] = self._generate_code()
        else:
            data["code"] = str(data["code"]).strip()
            self._assert_code_available(data["code"])
        return super().add(data)

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新：状态/归属/启停字段剔除（status 只经 publish、enabled 只经 toggleEnabled）。"""
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)
        data.pop("created_by", None)
        data.pop("enabled", None)
        if "code" in data:
            self._assert_code_available(data.get("code"), exclude_id=data.get("id"))
        if "tools" in data:
            tools = data.get("tools")
            data["tools"] = json.dumps(tools, ensure_ascii=False) if tools else None
        return super().update(data)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """软删：仅创建者或管理员。"""
        if current_user is not None and ids:
            for entity in self.session.exec(select(self.model).where(self.model.id.in_(ids))).all():
                if not _is_super_admin(current_user) and entity.created_by != current_user.id:
                    raise HTTPException(status_code=403, detail="仅创建者或管理员可删除该智能体")
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    # --- 可见性过滤（draft 仅创建者可见，管理员全量）---

    def _apply_query(self, statement, model, query, current_user=None, **kwargs):
        statement = super()._apply_query(statement, model, query, current_user, **kwargs)
        if current_user is not None and not _is_super_admin(current_user):
            statement = statement.where(or_(model.status != AGENT_STATUS_DRAFT, model.created_by == current_user.id))
        return statement

    # --- 出口：tools JSON 还原数组 ---

    def _finalize_data(self, data: Any) -> Any:
        rows = data if isinstance(data, list) else [data]
        for item in rows:
            if isinstance(item, dict) and isinstance(item.get("tools"), str):
                item["tools"] = json.loads(item["tools"]) if item["tools"].strip() else []
        return super()._finalize_data(data)

    # --- code 唯一性 ---

    def _generate_code(self) -> str:
        """编号自动生成：ag-{8位随机base36}；冲突重试 3 次，partial unique 兜底并发。"""
        import secrets

        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        for _ in range(3):
            candidate = "ag-" + "".join(secrets.choice(alphabet) for _ in range(8))
            if self._code_free(candidate):
                return candidate
        raise HTTPException(status_code=500, detail="标识生成冲突，请重试")

    def _code_free(self, code: str) -> bool:
        statement = select(self.model).where(
            self.model.code == code,
            self.model.delete_time == None,  # noqa: E711
        )
        return self.session.exec(statement).first() is None

    def _assert_code_available(self, code: Any, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(self.model).where(
            self.model.code == code,
            self.model.delete_time == None,  # noqa: E711
        )
        if exclude_id is not None:
            statement = statement.where(self.model.id != exclude_id)
        if self.session.exec(statement).first() is not None:
            raise HTTPException(status_code=400, detail=f"标识「{code}」已存在")
