"""评估运行回归对比：按 case_key 对齐两次运行，输出指标 diff 与单 case 退化/改善。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.model.enum import EvalRunStatus

# 单 case score 变化超过此阈值视为退化/改善
REGRESSION_SCORE_THRESHOLD = 0.1


def _run_metrics(run: WorkflowEvalRun) -> dict:
    return {
        "avgScore": run.avg_score,
        "passRate": run.pass_rate,
        "p95LatencyMs": run.p95_latency_ms,
        "totalCostMicroUsd": run.total_cost_micro_usd,
        "totalTokens": run.total_tokens,
    }


def compare_runs(
    session: Session, run_a_id: int, run_b_id: int, current_user=None
) -> dict:
    """对比两次评估运行（必须同测试集且均已完成）。run_b 相对 run_a 的变化。"""
    from app.modules.workflow_eval.service.eval_run_service import _assert_run_owned

    run_a = _assert_run_owned(session, run_a_id, current_user)
    run_b = _assert_run_owned(session, run_b_id, current_user)
    if run_a.test_set_id != run_b.test_set_id:
        raise HTTPException(status_code=400, detail="两个评估运行必须属于同一测试集才能对比")
    if run_a.status not in EvalRunStatus.TERMINAL or run_b.status not in EvalRunStatus.TERMINAL:
        raise HTTPException(status_code=400, detail="存在未完成的评估运行，无法对比")

    results_a = {
        r.case_key: r
        for r in session.exec(
            select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == run_a_id)
        ).all()
    }
    results_b = {
        r.case_key: r
        for r in session.exec(
            select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == run_b_id)
        ).all()
    }

    keys_a = set(results_a)
    keys_b = set(results_b)
    only_a = sorted(keys_a - keys_b)
    only_b = sorted(keys_b - keys_a)
    common = sorted(keys_a & keys_b)

    regressed: list[dict] = []
    improved: list[dict] = []
    for k in common:
        ra, rb = results_a[k], results_b[k]
        delta = round(rb.score - ra.score, 4)  # b 相对 a
        if delta <= -REGRESSION_SCORE_THRESHOLD:
            regressed.append({"caseKey": k, "scoreA": ra.score, "scoreB": rb.score, "delta": delta})
        elif delta >= REGRESSION_SCORE_THRESHOLD:
            improved.append({"caseKey": k, "scoreA": ra.score, "scoreB": rb.score, "delta": delta})

    ma, mb = _run_metrics(run_a), _run_metrics(run_b)
    metrics_diff = {
        "avgScore": round(mb["avgScore"] - ma["avgScore"], 4),
        "passRate": round(mb["passRate"] - ma["passRate"], 4),
        "p95LatencyMs": mb["p95LatencyMs"] - ma["p95LatencyMs"],
        "totalCostMicroUsd": mb["totalCostMicroUsd"] - ma["totalCostMicroUsd"],
    }

    return {
        "runA": {"id": run_a.id, "versionId": run_a.definition_version_id, "versionLabel": run_a.version_label, "metrics": ma},
        "runB": {"id": run_b.id, "versionId": run_b.definition_version_id, "versionLabel": run_b.version_label, "metrics": mb},
        "metricsDiff": metrics_diff,
        "onlyA": only_a,
        "onlyB": only_b,
        "common": common,
        "regressed": regressed,
        "improved": improved,
    }
