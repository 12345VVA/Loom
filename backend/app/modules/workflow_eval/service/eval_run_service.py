"""评估运行管理服务：发起评估、查看用例结果、取消。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow_eval.model.eval_run import (
    WorkflowEvalCaseResult,
    WorkflowEvalCaseResultRead,
    WorkflowEvalRun,
    WorkflowEvalRunRead,
)
from app.modules.workflow_eval.model.enum import EvalRunStatus
from app.modules.workflow_eval.model.test_set import WorkflowTestCase, WorkflowTestSet
from app.modules.workflow_eval.service.evaluator import EvaluatorRegistry

logger = logging.getLogger(__name__)


def _assert_run_owned(session: Session, eval_run_id: int, current_user: User | None) -> WorkflowEvalRun:
    """校验评估运行存在且归属当前用户（超管放行），返回 run。"""
    run = session.get(WorkflowEvalRun, eval_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评估运行不存在")
    if (
        current_user is not None
        and not getattr(current_user, "is_super_admin", False)
        and run.user_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="无权访问该评估运行")
    return run


class WorkflowEvalRunService(BaseAdminCrudService):
    """评估运行 CRUD + 发起/查看用例/取消。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowEvalRun)

    def start(self, payload: Any, current_user: User | None = None) -> dict:
        """创建评估运行（PENDING + 图快照）并投递 Celery 批量评估任务。返回 camelCase dict。"""
        test_set_id = payload.test_set_id
        test_set = self.session.get(WorkflowTestSet, test_set_id)
        if not test_set:
            raise HTTPException(status_code=404, detail="测试集不存在")

        definition_id = payload.definition_id or test_set.definition_id
        if definition_id is None:
            raise HTTPException(status_code=400, detail="测试集未关联工作流定义，请指定 definitionId")
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="工作流定义不存在")

        evaluator_type = payload.evaluator_type or "rule_match"
        if evaluator_type not in EvaluatorRegistry.available():
            raise HTTPException(status_code=400, detail=f"未知评估器类型: {evaluator_type}")

        # 空用例拦截；超量预警（完整分批/续跑为后续已知限制）
        case_count = self.session.exec(
            select(func.count()).select_from(
                select(WorkflowTestCase)
                .where(
                    WorkflowTestCase.test_set_id == test_set_id,
                    WorkflowTestCase.delete_time.is_(None),  # noqa: E711
                )
                .subquery()
            )
        ).one()
        if not case_count:
            raise HTTPException(status_code=400, detail="测试集没有用例，无法发起评估")
        if case_count > 100:
            logger.warning("测试集 %s 用例数较多（%d），批量评估可能耗时较长", test_set_id, case_count)

        run = WorkflowEvalRun(
            test_set_id=test_set_id,
            definition_id=definition_id,
            graph_json_snapshot=definition.graph_json,
            version_label=payload.version_label,
            status=EvalRunStatus.PENDING,
            user_id=current_user.id if current_user else None,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        from app.modules.workflow_eval.tasks.eval_tasks import run_eval_task

        task = run_eval_task.delay(run.id, evaluator_type)
        run.celery_task_id = task.id
        self.session.add(run)
        self.session.commit()
        return WorkflowEvalRunRead.model_validate(run).model_dump(by_alias=True)

    def list_cases(
        self, eval_run_id: int, current_user: User | None = None, page: int = 1, size: int = 20
    ) -> dict:
        """分页查询某次运行的用例结果（camelCase 出口，大输出按 storage_ref 还原）。"""
        _assert_run_owned(self.session, eval_run_id, current_user)

        total = self.session.exec(
            select(func.count()).select_from(
                select(WorkflowEvalCaseResult)
                .where(WorkflowEvalCaseResult.eval_run_id == eval_run_id)
                .subquery()
            )
        ).one()
        offset = (page - 1) * size
        items = list(
            self.session.exec(
                select(WorkflowEvalCaseResult)
                .where(WorkflowEvalCaseResult.eval_run_id == eval_run_id)
                .order_by(WorkflowEvalCaseResult.id)
                .offset(offset)
                .limit(size)
            ).all()
        )
        # 自定义路由不挂 response_model，需手动转 camelCase；大输出按 storage_ref 还原塞回 actualOutput
        from app.framework.storage import resolve_payload

        dicts = []
        for it in items:
            d = WorkflowEvalCaseResultRead.model_validate(it).model_dump(by_alias=True)
            if it.actual_output_storage_ref:
                d["actualOutput"] = resolve_payload(it.actual_output or "", it.actual_output_storage_ref)
            dicts.append(d)
        return {"list": dicts, "pagination": {"page": page, "size": size, "total": int(total or 0)}}

    def cancel(self, eval_run_id: int, current_user: User | None = None) -> dict:
        """取消评估：归属校验 + CAS pending/running→cancelled + revoke + 清理孤儿 case 实例。

        返回 {id, status, cancelled}；cancelled=False 表示运行已终结（无需/未能取消）。
        """
        run = _assert_run_owned(self.session, eval_run_id, current_user)
        result = self.session.execute(
            update(WorkflowEvalRun)
            .where(
                WorkflowEvalRun.id == eval_run_id,
                WorkflowEvalRun.status.in_([EvalRunStatus.PENDING, EvalRunStatus.RUNNING]),
            )
            .values(status=EvalRunStatus.CANCELLED, finished_at=datetime.utcnow())
        )
        cancelled = result.rowcount > 0
        if cancelled:
            # 清理本次评估已建、仍在 running 的 case 实例（CAS，不覆盖已终结状态）
            self.session.execute(
                update(WorkflowInstance)
                .where(
                    WorkflowInstance.id.in_(
                        select(WorkflowEvalCaseResult.workflow_instance_id).where(
                            WorkflowEvalCaseResult.eval_run_id == eval_run_id,
                            WorkflowEvalCaseResult.workflow_instance_id.is_not(None),  # noqa: E711
                        )
                    ),
                    WorkflowInstance.status == "running",
                )
                .values(status="cancelled")
            )
            self.session.commit()
            if run.celery_task_id:
                from app.celery_app import celery_app

                celery_app.control.revoke(run.celery_task_id, terminate=True)
        self.session.refresh(run)
        return {"id": run.id, "status": run.status, "cancelled": cancelled}
