"""批量评估编排同步辅助（被 eval_tasks 经 asyncio.to_thread 调用，不阻塞事件循环）。

每个函数自建独立 Session，避免跨 to_thread 共享会话。汇总用 CAS 终态迁移，
尊重 eval_run 已被 cancel 接口置为 cancelled 的情况。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, update
from sqlmodel import Session, select

from app.core.database import engine
from app.framework.storage import offload_payload
from app.modules.ai.model.ai import AiModelCallLog
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult, WorkflowEvalRun
from app.modules.workflow_eval.model.enum import CaseResultStatus, EvalRunStatus
from app.modules.workflow_eval.model.test_set import WorkflowTestCase, WorkflowTestSet

logger = logging.getLogger(__name__)


def percentile(values: list[int], p: float) -> int:
    """计算分位数（p∈(0,1]，nearest-rank）。空列表返回 0。"""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return int(s[k])


def load_eval_context(eval_run_id: int) -> dict | None:
    """加载评估运行上下文：run + cases + definition_id + graph 快照 + user_id。"""
    with Session(engine) as session:
        run = session.get(WorkflowEvalRun, eval_run_id)
        if not run:
            return None
        test_set = session.get(WorkflowTestSet, run.test_set_id)
        cases = list(
            session.exec(
                select(WorkflowTestCase)
                .where(WorkflowTestCase.test_set_id == run.test_set_id)
                .order_by(WorkflowTestCase.sort_order, WorkflowTestCase.id)
            ).all()
        )
        definition_id = run.definition_id or (test_set.definition_id if test_set else None)
        version_id = run.definition_version_id
        # 优先按 version_id 查版本表 graph；fallback 存量 run 的 graph_json_snapshot（旧 run）
        graph_snapshot = None
        if version_id is not None:
            from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

            v = session.get(WorkflowDefinitionVersion, version_id)
            graph_snapshot = json.loads(v.graph_json) if v and v.graph_json and v.graph_json != "{}" else None
        elif run.graph_json_snapshot and run.graph_json_snapshot != "{}":
            try:
                graph_snapshot = json.loads(run.graph_json_snapshot)
            except Exception:
                graph_snapshot = None
        return {
            "run_id": run.id,
            "definition_id": definition_id,
            "definition_version_id": version_id,
            "graph_json_snapshot": graph_snapshot,
            "user_id": run.user_id,
            "cases": cases,
        }


def mark_running(eval_run_id: int, celery_task_id: str | None) -> bool:
    """CAS pending→running，记 started_at + celery_task_id。"""
    with Session(engine) as session:
        result = session.execute(
            update(WorkflowEvalRun)
            .where(
                WorkflowEvalRun.id == eval_run_id,
                WorkflowEvalRun.status == EvalRunStatus.PENDING,
            )
            .values(
                status=EvalRunStatus.RUNNING,
                started_at=datetime.utcnow(),
                celery_task_id=celery_task_id,
            )
        )
        session.commit()
        return result.rowcount > 0


def mark_failed(eval_run_id: int, error_msg: str) -> bool:
    """CAS running→failed，写 error_message + finished_at（任务异常/超时收尾）。

    若 run 已被 cancel 或已终结（rowcount=0），不改状态，返回 False。
    用于 run_eval_task 的异常兜底与超时巡检，避免 run 永久停在 running。
    """
    with Session(engine) as session:
        result = session.execute(
            update(WorkflowEvalRun)
            .where(
                WorkflowEvalRun.id == eval_run_id,
                WorkflowEvalRun.status == EvalRunStatus.RUNNING,
            )
            .values(
                status=EvalRunStatus.FAILED,
                error_message=(error_msg or "")[:1000] or None,
                finished_at=datetime.utcnow(),
            )
        )
        session.commit()
        return result.rowcount > 0


def create_eval_instance(
    definition_id: int, definition_version_id: int | None, case: WorkflowTestCase, user_id: int | None
) -> int:
    """为单条用例创建运行实例（status=running，新 thread_id，记 version_id），返回 instance_id。"""
    inputs = json.loads(case.input_data) if case.input_data else {}
    with Session(engine) as session:
        instance = WorkflowInstance(
            definition_id=definition_id,
            version_id=definition_version_id,
            thread_id=str(uuid4()),
            status="running",
            state_data=json.dumps(inputs),
            current_node=None,
            user_id=user_id,
        )
        session.add(instance)
        session.flush()  # flush 取 id，避免 commit 后 expire_on_commit 再 refresh
        instance_id = instance.id
        session.commit()
        return instance_id


def read_instance_result(instance_id: int) -> dict:
    """读取实例终态 + workflow_output。"""
    with Session(engine) as session:
        inst = session.get(WorkflowInstance, instance_id)
        if not inst:
            return {"status": "error", "output": None, "error": "实例不存在", "final_vars": {}}
        final_vars = json.loads(inst.state_data) if inst.state_data else {}
        return {
            "status": inst.status,
            "output": final_vars.get("workflow_output"),
            "error": inst.error_message,
            "final_vars": final_vars,
        }


def cancel_eval_instance(instance_id: int) -> None:
    """超时收尾：CAS running→cancelled，避免孤儿实例。"""
    with Session(engine) as session:
        session.execute(
            update(WorkflowInstance)
            .where(
                WorkflowInstance.id == instance_id,
                WorkflowInstance.status == "running",
            )
            .values(status="cancelled")
        )
        session.commit()


def write_case_result(
    eval_run_id: int,
    case: WorkflowTestCase,
    instance_id: int | None,
    instance_result: dict,
    eval_result,  # EvalResult 或 None（执行失败时）
    evaluator_type: str,
    latency_ms: int,
    case_status: str | None = None,
) -> None:
    """写入单条用例结果。执行失败/超时覆盖 status，评分置 0。"""
    inst_status = instance_result.get("status")
    if case_status is None:
        if inst_status == "failed":
            case_status = CaseResultStatus.ERROR
        elif inst_status == "timeout":
            case_status = CaseResultStatus.TIMEOUT
        elif eval_result is not None:
            case_status = CaseResultStatus.SUCCESS if eval_result.passed else CaseResultStatus.FAIL
        else:
            case_status = CaseResultStatus.ERROR

    score = eval_result.score if (eval_result is not None and case_status in (CaseResultStatus.SUCCESS, CaseResultStatus.FAIL)) else 0.0
    passed = bool(eval_result and eval_result.passed and case_status == CaseResultStatus.SUCCESS)
    detail = json.dumps(eval_result.detail, ensure_ascii=False, default=str) if eval_result is not None else None
    output = instance_result.get("output")
    actual_json = json.dumps(output, ensure_ascii=False, default=str) if output is not None else None
    # T8：大输出分离到对象存储，主表存引用
    actual_inline, actual_ref = (offload_payload(actual_json) if actual_json else ("", None))

    with Session(engine) as session:
        # case 级 token/cost：按该 instance 聚合其全部 LLM 调用（节点执行 + judge）
        case_token = 0
        case_cost = 0
        if instance_id is not None:
            case_agg = session.exec(
                select(
                    func.sum(AiModelCallLog.total_tokens),
                    func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)),
                ).where(AiModelCallLog.workflow_instance_id == instance_id)
            ).one()
            case_token = int(case_agg[0] or 0)
            case_cost = int(case_agg[1] or 0)

        session.add(
            WorkflowEvalCaseResult(
                eval_run_id=eval_run_id,
                test_case_id=case.id,
                case_key=case.case_key,
                input_data=case.input_data,
                actual_output=actual_inline if actual_json else None,
                actual_output_storage_ref=actual_ref,
                expected_output=case.expected_output,
                score=score,
                passed=passed,
                latency_ms=latency_ms,
                token_total=case_token,
                cost_micro_usd=case_cost,
                status=case_status,
                evaluator_type=evaluator_type,
                evaluator_detail=detail,
                error_message=(instance_result.get("error") or "")[:1000] or None,
                workflow_instance_id=instance_id,
            )
        )
        session.commit()


def write_case_error(
    eval_run_id: int, case: WorkflowTestCase, instance_id: int | None, error_msg: str, latency_ms: int
) -> None:
    """单 case 异常隔离：写 error 结果，不拖垮整批。"""
    with Session(engine) as session:
        session.add(
            WorkflowEvalCaseResult(
                eval_run_id=eval_run_id,
                test_case_id=case.id,
                case_key=case.case_key,
                input_data=case.input_data,
                score=0.0,
                passed=False,
                latency_ms=latency_ms,
                status=CaseResultStatus.ERROR,
                evaluator_type="rule_match",
                error_message=(error_msg or "")[:1000] or None,
                workflow_instance_id=instance_id,
            )
        )
        session.commit()


def backfill_missing_results(eval_run_id: int, cases: list[WorkflowTestCase]) -> int:
    """补写未产生任何结果的 case 为 error，保证 finalize 的 total 与用例数一致。

    场景：_one 在 write_case_result/write_case_error 之前被 BaseException 中断，
    该 case 在 DB 无记录，finalize 的 total=len(results) 会小于真实用例数，
    导致 pass_rate 分母错误、回归对比缺行。此处对照 cases 补齐。
    """
    if not cases:
        return 0
    with Session(engine) as session:
        written_keys = set(
            session.exec(
                select(WorkflowEvalCaseResult.case_key).where(
                    WorkflowEvalCaseResult.eval_run_id == eval_run_id
                )
            ).all()
        )
    missing = [c for c in cases if c.case_key not in written_keys]
    for c in missing:
        logger.warning("评估运行 %d 用例 %s 未产生结果，补写 error", eval_run_id, c.case_key)
        write_case_error(eval_run_id, c, None, "用例执行未产生结果（可能因异常中断）", 0)
    return len(missing)


def finalize_eval_run(eval_run_id: int) -> None:
    """汇总指标 + CAS running→终态（尊重 cancelled）。"""
    with Session(engine) as session:
        run = session.get(WorkflowEvalRun, eval_run_id)
        if not run:
            return
        results = list(
            session.exec(
                select(WorkflowEvalCaseResult).where(WorkflowEvalCaseResult.eval_run_id == eval_run_id)
            ).all()
        )
        total = len(results)
        passed = sum(1 for r in results if r.status == CaseResultStatus.SUCCESS)
        failed = sum(1 for r in results if r.status == CaseResultStatus.FAIL)
        errored = sum(1 for r in results if r.status in (CaseResultStatus.ERROR, CaseResultStatus.TIMEOUT))

        scored = [r.score for r in results if r.status in (CaseResultStatus.SUCCESS, CaseResultStatus.FAIL)]
        avg_score = sum(scored) / len(scored) if scored else 0.0
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]

        # token/cost 精确聚合：按本次 run 关联的所有 workflow_instance_id 求和
        # （case 节点执行 + judge 的 LLM 调用均经 contextvar 打标到对应 instance，
        #   替代旧版按 user_id + 时间窗的近似聚合）
        now = datetime.utcnow()
        instance_ids = [r.workflow_instance_id for r in results if r.workflow_instance_id]
        token_total = 0
        cost_total = 0
        if instance_ids:
            agg = session.exec(
                select(
                    func.sum(AiModelCallLog.total_tokens),
                    func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)),
                ).where(AiModelCallLog.workflow_instance_id.in_(instance_ids))
            ).one()
            token_total = int(agg[0] or 0)
            cost_total = int(agg[1] or 0)

        if total == 0:
            final_status = EvalRunStatus.FAILED
        elif errored == total:
            # 全部用例异常/超时、无任何成功 → FAILED（区别于「部分成功」的 PARTIAL，避免误导运营）
            final_status = EvalRunStatus.FAILED
        elif errored == 0:
            final_status = EvalRunStatus.SUCCEEDED
        else:
            final_status = EvalRunStatus.PARTIAL

        # CAS running→终态；若已被 cancel 接口置 cancelled，rowcount=0，不改（尊重取消）
        session.execute(
            update(WorkflowEvalRun)
            .where(
                WorkflowEvalRun.id == eval_run_id,
                WorkflowEvalRun.status == EvalRunStatus.RUNNING,
            )
            .values(
                status=final_status,
                total=total,
                passed=passed,
                failed=failed,
                errored=errored,
                avg_score=round(avg_score, 4),
                pass_rate=round(passed / total, 4) if total else 0.0,
                p50_latency_ms=percentile(latencies, 0.5),
                p95_latency_ms=percentile(latencies, 0.95),
                p99_latency_ms=percentile(latencies, 0.99),
                max_latency_ms=max(latencies) if latencies else 0,
                total_tokens=token_total,
                total_cost_micro_usd=cost_total,
                finished_at=now,
            )
        )
        session.commit()


def sweep_timed_out_runs(timeout_seconds: int) -> int:
    """巡检：把 started_at 早于 now-timeout 仍 running 的 run CAS 置 failed。

    兜底 worker 进程级死亡（OOM kill）——run_eval_task 的 try/except 与 on_failure
    均无法捕获进程级死亡，run 会永久停在 running。由 Celery beat 周期调用。
    """
    threshold = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    with Session(engine) as session:
        stale_ids = list(
            session.exec(
                select(WorkflowEvalRun.id).where(
                    WorkflowEvalRun.status == EvalRunStatus.RUNNING,
                    WorkflowEvalRun.started_at.is_not(None),  # noqa: E711
                    WorkflowEvalRun.started_at < threshold,
                )
            ).all()
        )
    for rid in stale_ids:
        logger.warning("评估运行 %d 超时未终结（>%ds），置 failed", rid, timeout_seconds)
        mark_failed(rid, f"执行超时未终结（>{timeout_seconds}s，疑似 worker 异常）")
    return len(stale_ids)
