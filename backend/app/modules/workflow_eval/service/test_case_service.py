"""测试用例管理服务：CRUD + 维护所属测试集 items_count。"""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow_eval.model.test_set import WorkflowTestCase, WorkflowTestSet

# 值非空时必须为合法 JSON 字符串的字段
_JSON_FIELDS = ("input_data", "expected_output", "evaluator_config")


def _validate_json_fields(data: dict) -> None:
    """校验 JSON 字段：非空字符串时必须可被 json.loads。"""
    for key in _JSON_FIELDS:
        val = data.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, (dict, list)):
            continue
        try:
            json.loads(val)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail=f"{key} 不是合法 JSON")


class WorkflowTestCaseService(BaseAdminCrudService):
    """测试用例 CRUD，新增/删除时同步维护 WorkflowTestSet.items_count。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowTestCase, soft_delete=True)

    def _check_case_key_unique(self, test_set_id: int, case_key: str, exclude_id: int | None = None) -> None:
        stmt = select(WorkflowTestCase.id).where(
            WorkflowTestCase.test_set_id == test_set_id,
            WorkflowTestCase.case_key == case_key,
            WorkflowTestCase.delete_time.is_(None),  # noqa: E711
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkflowTestCase.id != exclude_id)
        if self.session.exec(stmt).first() is not None:
            raise HTTPException(status_code=400, detail=f"case_key 在集内已存在: {case_key}")

    def _before_add(self, data: dict) -> dict:
        _validate_json_fields(data)
        test_set_id = data.get("test_set_id")
        if not test_set_id or not self.session.get(WorkflowTestSet, test_set_id):
            raise HTTPException(status_code=400, detail="测试集不存在")
        self._check_case_key_unique(test_set_id, data.get("case_key"))
        return data

    def _after_add(self, entity, payload=None) -> None:
        # 原子自增：UPDATE ... SET items_count = items_count + 1，避免并发 read-modify-write 丢更新
        self.session.execute(
            update(WorkflowTestSet)
            .where(WorkflowTestSet.id == entity.test_set_id)
            .values(items_count=func.coalesce(WorkflowTestSet.items_count, 0) + 1)
        )
        self.session.commit()

    def _before_update(self, data: dict, entity) -> dict:
        _validate_json_fields(data)
        if data.get("case_key") and data["case_key"] != entity.case_key:
            self._check_case_key_unique(entity.test_set_id, data["case_key"], exclude_id=entity.id)
        return data

    def update(self, payload):
        """仅更新显式提供的字段，避免 None 覆盖 input_data 等 NOT NULL 列。"""
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(exclude_unset=True)
        else:
            data = {k: v for k, v in dict(payload).items() if v is not None}
        id_val = data.get("id")
        entity = self.session.get(self.model, id_val)
        if not entity:
            raise HTTPException(status_code=404, detail="用例不存在")
        data.pop("id", None)
        data = self._before_update(data, entity)
        for key, value in data.items():
            setattr(entity, key, value)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def delete(self, ids, payload=None, soft_delete=None):
        # 删除前记录受影响的 test_set，删除后重算其未删除用例数
        affected_ts = {
            c.test_set_id
            for c in self.session.exec(select(WorkflowTestCase).where(WorkflowTestCase.id.in_(list(ids)))).all()
        }
        result = super().delete(ids, payload, soft_delete)
        for ts_id in affected_ts:
            ts = self.session.get(WorkflowTestSet, ts_id)
            if ts:
                cnt = self.session.exec(
                    select(func.count()).select_from(
                        select(WorkflowTestCase)
                        .where(
                            WorkflowTestCase.test_set_id == ts_id,
                            WorkflowTestCase.delete_time.is_(None),  # noqa: E711
                        )
                        .subquery()
                    )
                ).one()
                ts.items_count = int(cnt or 0)
                self.session.add(ts)
        self.session.commit()
        return result
