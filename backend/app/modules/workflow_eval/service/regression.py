"""评估运行回归对比：按 case_key 对齐两次运行，输出指标 diff 与单 case 退化/改善。"""

from __future__ import annotations

import random

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.config import settings
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.model.enum import EvalRunStatus

# 单 case score 变化超过此阈值视为退化/改善（可由 settings.WORKFLOW_EVAL_REGRESSION_THRESHOLD 覆盖）
REGRESSION_SCORE_THRESHOLD = 0.1


def _regression_threshold() -> float:
    return float(getattr(settings, "WORKFLOW_EVAL_REGRESSION_THRESHOLD", REGRESSION_SCORE_THRESHOLD))


def _bootstrap_score_delta(scores_a: list[float], scores_b: list[float], n_boot: int = 1000) -> dict:
    """对配对 score（同 case_key 对齐）做 bootstrap 重采样，返回整体 delta + 95% CI + 显著性。

    delta = mean(B) - mean(A)（正=B 改善，负=B 退化）。CI 跨 0 即不显著。
    样本 < 5 时 bootstrap 不稳，仅报点估（sufficient=False）。
    """
    n = len(scores_a)
    if n == 0 or n != len(scores_b):
        return {"delta": 0.0, "ciLow": None, "ciHigh": None, "significant": False, "n": n, "sufficient": False}
    delta = (sum(scores_b) - sum(scores_a)) / n
    if n < 5:
        return {"delta": round(delta, 4), "ciLow": None, "ciHigh": None, "significant": False, "n": n, "sufficient": False}
    deltas: list[float] = []
    for _ in range(n_boot):
        idx = [random.randrange(n) for _ in range(n)]
        sa = sum(scores_a[i] for i in idx) / n
        sb = sum(scores_b[i] for i in idx) / n
        deltas.append(sb - sa)
    deltas.sort()
    lo = deltas[int(0.025 * n_boot)]
    hi = deltas[int(0.975 * n_boot)]
    significant = not (lo <= 0 <= hi)
    return {"delta": round(delta, 4), "ciLow": round(lo, 4), "ciHigh": round(hi, 4), "significant": significant, "n": n, "sufficient": True}


def _verdict(score_diff: dict, threshold: float) -> str:
    """整体判定：显著退化 / 显著改善 / 无显著变化 / 样本不足。"""
    if not score_diff.get("sufficient"):
        return "insufficient_sample"
    delta = score_diff["delta"]
    if score_diff["significant"] and delta <= -threshold:
        return "regression"
    if score_diff["significant"] and delta >= threshold:
        return "improvement"
    return "insignificant"


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

    threshold = _regression_threshold()
    regressed: list[dict] = []
    improved: list[dict] = []
    for k in common:
        ra, rb = results_a[k], results_b[k]
        delta = round(rb.score - ra.score, 4)  # b 相对 a
        if delta <= -threshold:
            regressed.append({"caseKey": k, "scoreA": ra.score, "scoreB": rb.score, "delta": delta})
        elif delta >= threshold:
            improved.append({"caseKey": k, "scoreA": ra.score, "scoreB": rb.score, "delta": delta})

    # 整体 score diff：bootstrap 置信区间 + 显著性判定（消除"阈值附近是噪声"的科学性硬伤）
    scores_a = [results_a[k].score for k in common]
    scores_b = [results_b[k].score for k in common]
    n_boot = int(getattr(settings, "WORKFLOW_EVAL_BOOTSTRAP_SAMPLES", 1000))
    score_diff = _bootstrap_score_delta(scores_a, scores_b, n_boot=n_boot)
    verdict = _verdict(score_diff, threshold)

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
        "scoreDiff": score_diff,
        "verdict": verdict,
        "onlyA": only_a,
        "onlyB": only_b,
        "common": common,
        "regressed": regressed,
        "improved": improved,
    }
