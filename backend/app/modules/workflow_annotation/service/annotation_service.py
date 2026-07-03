"""人工标注服务：CRUD + Cohen's κ judge 校准计算。"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow_annotation.model.annotation import WorkflowAnnotation
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.service.eval_run_service import _assert_run_owned

logger = logging.getLogger(__name__)


def _label_to_bool(label: str) -> int:
    """标注 label → 1/0（pass=1，其余=0），用于 κ 配对。"""
    return 1 if str(label).lower() in ("pass", "1", "true", "yes", "成功") else 0


def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float | None:
    """Cohen's κ（二分类）：(观察一致率 - 期望一致率) / (1 - 期望一致率)。

    返回 None 表示无配对样本；完全一致返回 1.0。
    """
    n = len(judge_labels)
    if n == 0 or n != len(human_labels):
        return None
    po = sum(1 for j, h in zip(judge_labels, human_labels) if j == h) / n
    p_judge = sum(judge_labels) / n
    p_human = sum(human_labels) / n
    pe = p_judge * p_human + (1 - p_judge) * (1 - p_human)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return round((po - pe) / (1 - pe), 4)


def _kappa_level(kappa: float | None) -> str:
    """κ 可信度等级：≥0.6 可信 / 0.4-0.6 中等 / <0.4 不可信 / 无标注。"""
    if kappa is None:
        return "no_annotation"
    if kappa >= 0.6:
        return "reliable"
    if kappa >= 0.4:
        return "moderate"
    return "unreliable"


class WorkflowAnnotationService(BaseAdminCrudService):
    """人工标注 CRUD + κ 校准。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowAnnotation)

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增标注，自动写入 annotator_user_id，并校验当前用户是否拥有该评估运行。"""
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        if current_user is not None and "annotator_user_id" not in data:
            data["annotator_user_id"] = current_user.id

        # 归属校验：通过 case_result_id 找到 eval_run_id，校验当前用户是否拥有该 run
        case_result_id = data.get("case_result_id")
        if case_result_id is not None and current_user is not None:
            case_result = self.session.get(WorkflowEvalCaseResult, case_result_id)
            if case_result is None:
                # 关联用例不存在：不可放行（否则绕过归属校验产生孤儿标注）
                raise HTTPException(status_code=404, detail="关联的评估用例结果不存在")
            _assert_run_owned(self.session, case_result.eval_run_id, current_user)

        return super().add(data)

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新标注前校验归属：通过 case_result → eval_run 校验当前用户拥有该 run。"""
        if current_user is not None:
            id_val = getattr(payload, "id", None)
            if id_val is not None:
                ann = self.session.get(WorkflowAnnotation, id_val)
                if ann is not None:
                    cr = self.session.get(WorkflowEvalCaseResult, ann.case_result_id)
                    if cr is not None:
                        _assert_run_owned(self.session, cr.eval_run_id, current_user)
        return super().update(payload)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除标注前校验归属：每条标注对应的 eval_run 须归属当前用户。"""
        if current_user is not None and ids:
            anns = list(
                self.session.exec(
                    select(WorkflowAnnotation).where(WorkflowAnnotation.id.in_(ids))
                ).all()
            )
            for ann in anns:
                cr = self.session.get(WorkflowEvalCaseResult, ann.case_result_id)
                if cr is not None:
                    _assert_run_owned(self.session, cr.eval_run_id, current_user)
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    def compute_kappa(self, eval_run_id: int, current_user: User | None = None) -> dict:
        """计算某评估运行的 judge 与人工标注的 Cohen's κ，回填 run.summary_payload.judge_calibration。

        每 case_result 取一条标注（is_gold 优先，否则最新），与 case_result.passed 配对算 κ。
        """
        # 归属校验：复用 workflow_eval 模块的 _assert_run_owned（超管放行，非 owner 抛 403）
        run = _assert_run_owned(self.session, eval_run_id, current_user)

        case_results = list(
            self.session.exec(
                select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == eval_run_id)
            ).all()
        )
        cr_by_id = {cr.id: cr for cr in case_results}

        # 取这些 case_result 的标注（gold 优先，否则最新）
        ann_by_cr: dict[int, WorkflowAnnotation] = {}
        if cr_by_id:
            annotations = list(
                self.session.exec(
                    select(WorkflowAnnotation).where(
                        WorkflowAnnotation.case_result_id.in_(list(cr_by_id.keys()))
                    )
                ).all()
            )
            for a in annotations:
                cur = ann_by_cr.get(a.case_result_id)
                if cur is None or (a.is_gold and not cur.is_gold):
                    ann_by_cr[a.case_result_id] = a
                elif a.is_gold == cur.is_gold and a.id > cur.id:
                    ann_by_cr[a.case_result_id] = a

        judge_labels: list[int] = []
        human_labels: list[int] = []
        for cr_id, ann in ann_by_cr.items():
            judge_labels.append(1 if cr_by_id[cr_id].passed else 0)
            human_labels.append(_label_to_bool(ann.label))

        n = len(judge_labels)
        kappa = cohen_kappa(judge_labels, human_labels)
        agreement = (sum(1 for j, h in zip(judge_labels, human_labels) if j == h) / n) if n else 0.0
        result = {
            "kappa": kappa,
            "agreementRate": round(agreement, 4),
            "n": n,
            "judgePass": sum(judge_labels),
            "humanPass": sum(human_labels),
            "level": _kappa_level(kappa),
        }

        # 回填 run.summary_payload.judge_calibration
        payload = json.loads(run.summary_payload) if run.summary_payload else {}
        payload["judge_calibration"] = result
        run.summary_payload = json.dumps(payload, ensure_ascii=False)
        self.session.add(run)
        self.session.commit()
        return result
