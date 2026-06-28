"""工作流批量评估 Celery 任务。

在独立事件循环内并发跑各 case：每 case 建真实 WorkflowInstance 并 await _async_execute
（复用 flush 落库/CAS/checkpointer/治理/SSE 全链路，方案 A），用 Semaphore 控并发、
wait_for 控单 case 超时。单 case 异常隔离（return_exceptions + try/except）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

# Windows psycopg 异步需 SelectorEventLoop（与 workflow_tasks 一致）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.core.logging import workflow_instance_id_ctx
from app.celery_app import celery_app
from app.modules.workflow.tasks.workflow_tasks import _async_execute
from app.modules.workflow_eval.model.enum import CaseResultStatus
from app.modules.workflow_eval.service.eval_orchestrator import (
    backfill_missing_results,
    cancel_eval_instance,
    create_eval_instance,
    evaluate_node_evaluators,
    finalize_eval_run,
    load_eval_context,
    mark_failed,
    mark_running,
    read_instance_result,
    write_case_error,
    write_case_result,
)
from app.modules.workflow_eval.service.evaluator import EvaluatorRegistry, EvalContext
from app.modules.workflow_eval.service.evaluator.llm_judge import build_default_judge_fn

logger = logging.getLogger(__name__)

# 并发 case 数与单 case 超时（后续可配置化到 settings）
MAX_CONCURRENT_CASES = 4
CASE_TIMEOUT_SECONDS = 600
# 单次评估运行硬超时（与 run_eval_task 的 task_time_limit 对齐 + buffer）：
# 超过仍 running 视为 worker 进程级死亡（OOM kill），由 sweep 巡检兜底置 failed
EVAL_RUN_TIMEOUT_SECONDS = 4 * 60 * 60 + 15 * 60


@celery_app.task(
    name="workflow.eval.run",
    bind=True,
    max_retries=0,
    task_time_limit=4 * 60 * 60,  # 4h：批量评估可能跑较久（4 并发 × 600s/批）
)
def run_eval_task(self, eval_run_id: int, evaluator_type: str = "rule_match"):
    """批量评估入口。evaluator_type 由发起请求传入（不落 eval_run 字段）。

    try/except 兜底：_async_run_eval 抛非 case 级异常时（事件循环崩溃、finalize
    DB 异常等），把 run CAS 为 failed 并写 error_message，避免永久 running。
    """
    try:
        asyncio.run(_async_run_eval(eval_run_id, self.request.id, evaluator_type))
    except Exception as exc:
        logger.error("评估任务 run_id=%d 异常终止: %s", eval_run_id, exc, exc_info=True)
        try:
            if not mark_failed(eval_run_id, f"评估任务异常: {exc}"):
                logger.warning("评估运行 %d 未置 failed（可能已被取消或已终结）", eval_run_id)
        except Exception:
            logger.error("标记评估运行 %d 为 failed 时再次异常", eval_run_id, exc_info=True)


async def _async_run_eval(eval_run_id: int, celery_task_id: str | None, evaluator_type: str) -> None:
    ctx = await asyncio.to_thread(load_eval_context, eval_run_id)
    if ctx is None:
        logger.error("评估运行 %d 不存在", eval_run_id)
        return

    definition_id: int | None = ctx["definition_id"]
    graph_snapshot: dict | None = ctx["graph_json_snapshot"]
    user_id = ctx["user_id"]
    cases = ctx["cases"]

    if not definition_id:
        logger.error("评估运行 %d 未关联 definition，无法执行", eval_run_id)
        return

    if not await asyncio.to_thread(mark_running, eval_run_id, celery_task_id):
        logger.info("评估运行 %d 已被取消或非 pending，停止执行", eval_run_id)
        return

    sem = asyncio.Semaphore(MAX_CONCURRENT_CASES)

    async def _one(case: Any) -> None:
        async with sem:
            instance_id: int | None = None
            start_t = time.perf_counter()
            try:
                instance_id = await asyncio.to_thread(
                    create_eval_instance, definition_id, ctx["definition_version_id"], case, user_id
                )
                inputs = json.loads(case.input_data) if case.input_data else {}

                # 复用 _async_execute 全链路；用 graph 快照保证回归可比
                try:
                    await asyncio.wait_for(
                        _async_execute(
                            instance_id,
                            definition_id,
                            inputs,
                            None,
                            version_id=ctx["definition_version_id"],
                            graph_json_override=graph_snapshot,
                        ),
                        timeout=CASE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await asyncio.to_thread(cancel_eval_instance, instance_id)
                    latency_ms = int((time.perf_counter() - start_t) * 1000)
                    await asyncio.to_thread(
                        write_case_result,
                        eval_run_id, case, instance_id,
                        {"status": "timeout", "output": None, "error": "执行超时"},
                        None, evaluator_type, latency_ms, CaseResultStatus.TIMEOUT,
                    )
                    return

                instance_result = await asyncio.to_thread(read_instance_result, instance_id)
                latency_ms = int((time.perf_counter() - start_t) * 1000)

                # 实例执行失败：记 error，不评估
                if instance_result.get("status") == "failed":
                    await asyncio.to_thread(
                        write_case_result, eval_run_id, case, instance_id, instance_result,
                        None, evaluator_type, latency_ms, CaseResultStatus.ERROR,
                    )
                    return

                # 评估：期望值 expected_output(JSON) 优先，其次 expected_text
                expected: Any = None
                if case.expected_output:
                    try:
                        expected = json.loads(case.expected_output)
                    except json.JSONDecodeError:
                        expected = case.expected_output
                elif case.expected_text:
                    expected = case.expected_text

                case_cfg = json.loads(case.evaluator_config) if case.evaluator_config else {}
                if case.expected_text:
                    case_cfg.setdefault("expected_text", case.expected_text)

                # llm_judge：注入复用 run_ai_chat 的默认 judge_fn（用例级 profile 优先，全局兜底）
                if evaluator_type == "llm_judge" and "judge_fn" not in case_cfg:
                    profile_code = case_cfg.get("judge_profile_code") or settings.WORKFLOW_EVAL_JUDGE_PROFILE
                    if profile_code:
                        case_cfg["judge_fn"] = build_default_judge_fn(
                            profile_code,
                            prompt_template=case_cfg.get("judge_prompt"),
                            rubric=case_cfg.get("rubric"),
                            samples=case_cfg.get("samples"),
                        )
                    else:
                        logger.warning(
                            "评估运行 %d 用例 %s：llm_judge 未配置 judge_profile_code（用例级/全局均空），返回中性分",
                            eval_run_id, case.case_key,
                        )

                evaluator = EvaluatorRegistry.get(evaluator_type)
                eval_ctx = EvalContext(
                    input_data=inputs,
                    expected=expected,
                    actual=instance_result.get("output"),
                    case_config=case_cfg,
                )
                # judge/composite 的 LLM 调用归属当前 case instance（节点路径已由 _async_execute set 覆盖）
                _judge_ctx_token = workflow_instance_id_ctx.set(instance_id)
                try:
                    # llm_judge 含同步 LLM 调用，用 to_thread 卸载避免阻塞事件循环（否则 case 并发失效）
                    if evaluator_type == "llm_judge":
                        eval_result = await asyncio.to_thread(evaluator.evaluate, eval_ctx)
                    else:
                        eval_result = evaluator.evaluate(eval_ctx)
                finally:
                    workflow_instance_id_ctx.reset(_judge_ctx_token)
                # P1-1 trace：节点级评估（读 WorkflowExecutionLog，不侵入执行链路）
                node_results = None
                node_evaluators = case_cfg.get("node_evaluators")
                if node_evaluators and isinstance(node_evaluators, dict) and instance_id:
                    try:
                        node_results = await asyncio.to_thread(
                            evaluate_node_evaluators, instance_id, node_evaluators, case_cfg
                        )
                    except Exception as exc:
                        logger.warning("评估运行 %d 用例 %s 节点评估异常: %s", eval_run_id, case.case_key, exc)
                    # 综合通过：node_fail_overall 时，任一 node fail → 整体 fail
                    if (
                        node_results
                        and case_cfg.get("node_fail_overall")
                        and any(not nr.get("passed") for nr in node_results)
                    ):
                        eval_result.passed = False
                await asyncio.to_thread(
                    write_case_result, eval_run_id, case, instance_id, instance_result,
                    eval_result, evaluator_type, latency_ms, node_results,
                )
            except Exception as e:
                logger.error("评估用例 %s 异常: %s", getattr(case, "case_key", "?"), e, exc_info=True)
                latency_ms = int((time.perf_counter() - start_t) * 1000)
                try:
                    await asyncio.to_thread(write_case_error, eval_run_id, case, instance_id, str(e), latency_ms)
                except Exception:
                    logger.error("写入 case 错误结果失败", exc_info=True)

    gather_results = await asyncio.gather(*[_one(c) for c in cases], return_exceptions=True)

    # 问题3：_one 内部已 try/except，但 BaseException（KeyboardInterrupt/SystemExit 等）
    # 会逃逸到 gather 返回值（return_exceptions=True 不重抛），此处补日志。
    for r in gather_results:
        if isinstance(r, BaseException):
            logger.warning("评估用例 gather 返回异常实例: %s", r, exc_info=r)

    # 补写未产生任何结果的 case（如 _one 写入前被 BaseException 中断），
    # 保证 finalize 的 total = 用例数，pass_rate 分母正确、回归对比完整。
    await asyncio.to_thread(backfill_missing_results, eval_run_id, cases)

    await asyncio.to_thread(finalize_eval_run, eval_run_id)


@celery_app.task(name="workflow.eval.sweep_timeouts")
def sweep_timed_out_eval_runs() -> None:
    """周期巡检超时未终结的评估运行（兜底 worker 进程级死亡/OOM kill）。"""
    from app.modules.workflow_eval.service.eval_orchestrator import sweep_timed_out_runs

    swept = sweep_timed_out_runs(EVAL_RUN_TIMEOUT_SECONDS)
    if swept:
        logger.info("巡检回收 %d 个超时评估运行", swept)
