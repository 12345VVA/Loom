"""测试集管理服务。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow_eval.model.test_set import WorkflowTestCase, WorkflowTestSet


class WorkflowTestSetService(BaseAdminCrudService):
    """测试集 CRUD + 批量导入用例。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowTestSet)

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增测试集，注入 owner。"""
        if isinstance(payload, list):
            return [self.add(item, current_user) for item in payload]
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        if current_user is not None and "user_id" not in data:
            data["user_id"] = current_user.id
        return super().add(data)

    def import_cases(self, test_set_id: int, cases: list[dict]) -> dict:
        """批量导入用例，校验 case_key 集内唯一。"""
        test_set = self.session.get(WorkflowTestSet, test_set_id)
        if not test_set:
            raise HTTPException(status_code=404, detail="测试集不存在")

        existing_keys = set(
            self.session.exec(
                select(WorkflowTestCase.case_key).where(WorkflowTestCase.test_set_id == test_set_id)
            ).all()
        )
        new_keys: set[str] = set()
        added = 0
        for idx, item in enumerate(cases):
            key = item.get("case_key")
            if not key:
                raise HTTPException(status_code=400, detail=f"第 {idx + 1} 条用例缺少 case_key")
            if key in existing_keys or key in new_keys:
                raise HTTPException(status_code=400, detail=f"case_key 重复: {key}")
            new_keys.add(key)
            self.session.add(
                WorkflowTestCase(
                    test_set_id=test_set_id,
                    case_key=key,
                    input_data=json.dumps(item.get("input_data") or {}, ensure_ascii=False),
                    expected_output=(
                        json.dumps(item["expected_output"], ensure_ascii=False)
                        if item.get("expected_output") is not None
                        else None
                    ),
                    expected_text=item.get("expected_text"),
                    evaluator_config=(
                        json.dumps(item["evaluator_config"], ensure_ascii=False)
                        if item.get("evaluator_config")
                        else None
                    ),
                    weight=float(item.get("weight", 1.0)),
                    sort_order=int(item.get("sort_order", idx)),
                )
            )
            added += 1

        # 原子自增：UPDATE ... SET items_count = items_count + added，避免并发导入丢更新
        self.session.execute(
            update(WorkflowTestSet)
            .where(WorkflowTestSet.id == test_set_id)
            .values(items_count=func.coalesce(WorkflowTestSet.items_count, 0) + added)
        )
        self.session.commit()
        self.session.refresh(test_set)
        return {"imported": added, "itemsCount": test_set.items_count}
