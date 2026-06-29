"""
工作流 Celery 异步任务入口。
将工作流执行从 Web 进程剥离到独立 Worker，避免进程重启丢失运行中实例。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

# Windows 上 psycopg 异步模式不兼容默认的 ProactorEventLoop，需切换为 SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.celery_app import celery_app
from app.core.database import Session, engine
from app.core.logging import workflow_instance_id_ctx
from sqlmodel import select
from sqlalchemy import update
from app.modules.ai.service.security_service import AiSecurityService
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
from app.modules.workflow.service.checkpointer import get_async_checkpointer
from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.event_bus import publish_event
import app.modules.workflow.service.workflow_service as _workflow_service  # noqa: F401  冗余保险：compile_graph 入口已确保注册，此处保留双保险以防漏

logger = logging.getLogger(__name__)

# T4：批量落库参数。节点日志先入 asyncio.Queue，由后台 flush_worker 按「批大小或时间间隔」
# 通过 asyncio.to_thread 批量 commit，避免每节点一次 commit 阻塞执行事件循环。
_FLUSH_BATCH_SIZE = 10
_FLUSH_INTERVAL_SECONDS = 0.2
_FLUSH_DRAIN_TIMEOUT_SECONDS = 30
_FLUSH_SENTINEL = object()


def _maybe_offload(content: str) -> tuple[str, str | None]:
    """T8：超阈值载荷落对象存储。委托 storage.offload_payload（workflow/eval 共用）。"""
    from app.framework.storage import offload_payload

    return offload_payload(content)


def _persist_node_payloads_sync(instance_id: int, payloads: list[dict]) -> None:
    """同步批量落库：对每个 payload 更新 instance 推进度 + 插入 exec_log，单次 commit。

    T6：input 引用上一条 log 的 output（ref_prev）消除冗余；首条 full。
    T8：output（及首条 input）超阈值时分离到对象存储，主表存引用。
    payloads 的 input_data/output_data 已在入队前完成脱敏（T5），不削弱 audit S2。
    被 _flush_worker 经 asyncio.to_thread 调用，不阻塞执行事件循环。
    """
    if not payloads:
        return
    with Session(engine) as session:
        # 批首查 instance 最后一条 log id，作为本批首条 ref_prev 的 base
        prev_log_id = session.exec(
            select(WorkflowExecutionLog.id)
            .where(WorkflowExecutionLog.instance_id == instance_id)
            .order_by(WorkflowExecutionLog.id.desc())
            .limit(1)
        ).first()

        inst = session.get(WorkflowInstance, instance_id)
        for p in payloads:
            if inst and inst.status != "cancelled":
                inst.current_node = p["node_id"]
                inst.state_data = p["state_data"]
                session.add(inst)

            # output 始终 full，走 T8 offload
            output_inline, output_ref = _maybe_offload(p["output_data"])
            # input：首条 full（走 T8 offload）；后续 ref_prev（不存内容）
            if prev_log_id is None:
                payload_type = "full"
                input_inline, input_ref = _maybe_offload(p["input_data"])
                diff_base_log_id = None
            else:
                payload_type = "ref_prev"
                input_inline, input_ref = "REF_PREV", None
                diff_base_log_id = prev_log_id

            log = WorkflowExecutionLog(
                instance_id=instance_id,
                node_id=p["node_id"],
                node_name=p["node_name"],
                node_type=p["node_type"],
                input_data=input_inline,
                output_data=output_inline,
                input_storage_ref=input_ref,
                output_storage_ref=output_ref,
                payload_type=payload_type,
                diff_base_log_id=diff_base_log_id,
                latency_ms=p["latency_ms"],
                status="success",
            )
            session.add(log)
            session.flush()  # 取 log.id 作为下一条 ref_prev 的 base
            prev_log_id = log.id
        session.commit()


def _is_cancelled_sync(instance_id: int) -> bool:
    """协作式取消探活：读取 instance.status 是否已被 cancel_instance 置为 cancelled。"""
    with Session(engine) as session:
        inst = session.get(WorkflowInstance, instance_id)
        return bool(inst and inst.status == "cancelled")


async def _flush_worker(instance_id: int, queue: asyncio.Queue) -> None:
    """后台批量落库协程：按批大小或时间间隔 flush，收到 SENTINEL 则处理剩余后退出。

    Queue/Task 均在 _async_execute 的 asyncio.run 事件循环内创建与销毁，不跨 Celery prefork
    fork 复用。单消费者保证节点日志 FIFO。
    """
    batch: list[dict] = []
    last_flush = time.perf_counter()
    while True:
        timeout = max(0.01, _FLUSH_INTERVAL_SECONDS - (time.perf_counter() - last_flush))
        try:
            item = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            if batch:
                await asyncio.to_thread(_persist_node_payloads_sync, instance_id, batch)
                batch.clear()
            last_flush = time.perf_counter()
            continue

        if item is _FLUSH_SENTINEL:
            if batch:
                await asyncio.to_thread(_persist_node_payloads_sync, instance_id, batch)
            return

        batch.append(item)
        if len(batch) >= _FLUSH_BATCH_SIZE:
            await asyncio.to_thread(_persist_node_payloads_sync, instance_id, batch)
            batch.clear()
            last_flush = time.perf_counter()


async def _drain_flush(queue: asyncio.Queue, task: asyncio.Task) -> None:
    """收尾：通知 flush_worker 处理剩余 batch 并退出，保证退出前日志已落库。"""
    await queue.put(_FLUSH_SENTINEL)
    try:
        await asyncio.wait_for(task, timeout=_FLUSH_DRAIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("工作流 flush_worker 收尾超时，强制取消")
        task.cancel()


def _mark_instance_failed(instance_id: int, message: str, expected: str = "running") -> None:
    """Celery 任务入口兜底：把实例置为 failed 并发布事件（仅当当前状态==expected，避免覆盖 cancelled）。

    用于 execute_workflow 在 asyncio.run 之前就失败的场景（如参数 JSON 解析失败）：
    此时实例仍为 running，若不主动写终态，需等进程重启由 recover_orphaned_instances 兜底（最长 30 分钟）。
    """
    try:
        with Session(engine) as session:
            result = session.execute(
                update(WorkflowInstance)
                .where(WorkflowInstance.id == instance_id, WorkflowInstance.status == expected)
                .values(status="failed", error_message=(message or "")[:500])
            )
            session.commit()
            if result.rowcount:
                publish_event(instance_id, "failed", {"status": "failed", "error": message})
    except Exception as se:
        logger.error("记录工作流实例 %d failed 终态失败: %s", instance_id, se, exc_info=True)


@celery_app.task(
    name="workflow.execute",
    bind=True,
    max_retries=0,
    task_time_limit=30 * 60,
)
def execute_workflow(self, instance_id: int, definition_id: int, initial_vars_json: str, resume_val_json: str = None):
    """
    在 Celery Worker 中执行或恢复一个工作流实例。
    """
    try:
        initial_vars = json.loads(initial_vars_json)
        resume_val = json.loads(resume_val_json) if resume_val_json else None
    except (json.JSONDecodeError, TypeError) as e:
        # 参数 JSON 畸形：立即写 failed 终态，避免实例假死在 running（否则需进程重启兜底）
        _mark_instance_failed(instance_id, f"初始参数解析失败: {e}")
        logger.error("工作流 %d 参数 JSON 解析失败: %s", instance_id, e)
        return
    asyncio.run(_async_execute(instance_id, definition_id, initial_vars, resume_val))


@celery_app.task(name="workflow.version.sweep_archived")
def sweep_archived_versions() -> None:
    """周期清理过期归档工作流版本（兜底版本表无限增长，跳过被引用版本）。"""
    from app.modules.workflow.service.workflow_version_service import WorkflowVersionService

    with Session(engine) as session:
        swept = WorkflowVersionService(session).sweep_old_archived()
    if swept:
        logger.info("清理 %d 个过期归档工作流版本", swept)


async def _async_execute(
    instance_id: int,
    definition_id: int,
    initial_vars: dict,
    resume_val: Any = None,
    *,
    version_id: int | None = None,
    graph_json_override: dict | None = None,
):
    """异步工作流执行体，逻辑与 WorkflowInstanceService._run_workflow 对齐。

    graph_json_override：评估等场景传入已解析的图快照，避免依赖 definition 当前版本（回归可比）；
    默认 None 时从 definition.graph_json 读取（正式执行路径，行为不变）。
    """
    from langgraph.types import Command
    from sqlalchemy import update

    from app.core.config import settings

    node_timeout = settings.WORKFLOW_NODE_TIMEOUT

    def _cas(session, expected_status: str, **values) -> int:
        """对实例做条件更新（仅当当前状态等于 expected_status），返回受影响行数。
        避免执行循环的终态写入覆盖已被 cancel_instance 写入的 cancelled 状态。
        """
        result = session.execute(
            update(WorkflowInstance)
            .where(WorkflowInstance.id == instance_id, WorkflowInstance.status == expected_status)
            .values(**values)
        )
        return result.rowcount

    # T4：批量落库后台协程（在 try 外创建，使外层 except 兜底可 drain；flush_worker 只用 engine，不依赖 checkpointer）
    flush_queue: asyncio.Queue = asyncio.Queue()
    flush_task = asyncio.create_task(_flush_worker(instance_id, flush_queue))

    # 设置 contextvar：本次实例的所有 LLM 调用（节点执行）按 instance 打标，
    # 供 workflow_eval 按 instance 精确聚合 token/cost（runtime_service._log_call 读取）
    _inst_ctx_token = workflow_instance_id_ctx.set(instance_id)

    try:
        # 1. 编译拓扑
        with Session(engine) as session:
            instance = session.get(WorkflowInstance, instance_id)
            definition = session.get(WorkflowDefinition, definition_id)
            if not instance or not definition:
                logger.error("工作流执行失败: 找不到实例 %d 或定义 %d", instance_id, definition_id)
                return
            thread_id = instance.thread_id
            # 版本解析优先级：graph_json_override（eval 存量 fallback）> version_id > instance.version_id
            # > definition.current_version_id。graph_json 现已存版本表（纯版本表模型）。
            if graph_json_override is not None:
                graph_json = graph_json_override
            else:
                effective_vid = version_id or instance.version_id or definition.current_version_id
                if effective_vid is None:
                    logger.error("工作流执行失败: 实例 %d 无可用版本（未发布？）", instance_id)
                    return
                version = session.get(WorkflowDefinitionVersion, effective_vid)
                if not version:
                    logger.error("工作流执行失败: 版本 %d 不存在", effective_vid)
                    return
                graph_json = json.loads(version.graph_json)
        logger.info(
            "[Workflow] Compiling graph: instance=%d, nodes=%s, edges=%s",
            instance_id,
            [n.get("id") for n in graph_json.get("nodes", [])],
            [(e.get("source"), e.get("target"), e.get("type")) for e in graph_json.get("edges", [])],
        )
        graph = WorkflowCompiler.compile_graph(graph_json)

        async with get_async_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            logger.info("[Workflow] Graph compiled successfully, instance=%d", instance_id)

            config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}

            # 2. 区分启动与恢复
            if resume_val is not None:
                events = compiled.astream(Command(resume=resume_val), config=config, stream_mode="updates")
            else:
                initial_state = {"messages": [], "variables": initial_vars, "current_node": "start"}
                events = compiled.astream(initial_state, config=config, stream_mode="updates")

            last_step_time = time.perf_counter()
            current_vars = initial_vars
            event_count = 0

            # 预先构建节点字典映射，避免在事件循环中进行 O(N) 线性查找性能损耗
            nodes_map = {node["id"]: node for node in graph_json.get("nodes", [])}

            # 3. 迭代执行事件
            # 用 wait_for 包装 __anext__ 实现单节点超时（卡死节点不再烧满 30 分钟硬上限）；
            # 协作式取消：每个节点回查 instance.status，被 cancel_instance 置为 cancelled 则优雅退出。
            ait = events.__aiter__()
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(ait.__anext__(), timeout=node_timeout)
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        await _drain_flush(flush_queue, flush_task)
                        with Session(engine) as session:
                            _cas(session, "running", status="failed", error_message=f"节点执行超时（{node_timeout}秒）")
                            session.commit()
                        logger.warning("[Workflow] 节点执行超时 instance=%d (%ds)", instance_id, node_timeout)
                        publish_event(instance_id, "failed", {"status": "failed", "error": "节点执行超时"})
                        return

                    for node_id, node_output in event.items():
                        event_count += 1
                        current_time = time.perf_counter()
                        latency_ms = int((current_time - last_step_time) * 1000)
                        last_step_time = current_time

                        if node_id == "__interrupt__":
                            # 中断前先把已入队的日志落库，再写 paused 终态
                            await _drain_flush(flush_queue, flush_task)
                            with Session(engine) as session:
                                inst = session.get(WorkflowInstance, instance_id)
                                current_node_name = "human_input"
                                if inst:
                                    # 不覆盖 cancelled：若执行期间用户已取消，按取消收尾
                                    if inst.status == "cancelled":
                                        session.commit()
                                        publish_event(instance_id, "cancelled", {"status": "cancelled"})
                                        return
                                inst.status = "paused"
                                inst.current_node = inst.current_node or "human_input"
                                session.add(inst)
                                session.commit()
                                current_node_name = inst.current_node

                            publish_event(
                                instance_id,
                                "paused",
                                {
                                    "node_id": current_node_name,
                                    "status": "paused",
                                },
                            )
                            return

                        new_vars = node_output.get("variables", {})
                        logger.info(
                            "[Workflow] Event #%d: node=%s, vars_keys=%s, instance=%d",
                            event_count,
                            node_id,
                            list(new_vars.keys()) if isinstance(new_vars, dict) else None,
                            instance_id,
                        )

                        # 协作式取消：同步探活 instance.status，被 cancel 则 drain 后退出
                        if await asyncio.to_thread(_is_cancelled_sync, instance_id):
                            await _drain_flush(flush_queue, flush_task)
                            logger.info("[Workflow] 实例 %d 已取消，停止执行", instance_id)
                            publish_event(instance_id, "cancelled", {"status": "cancelled"})
                            return

                        node_info = nodes_map.get(node_id, {})
                        # T5：脱敏 + 序列化在入队前完成，保证落库 payload 已脱敏（不削弱 audit S2）。
                        # 脱敏副本同时用于 SSE 推送，避免重复脱敏。
                        input_masked = AiSecurityService.mask_sensitive_dict(current_vars)
                        output_masked = AiSecurityService.mask_sensitive_dict(new_vars)
                        await flush_queue.put(
                            {
                                "node_id": node_id,
                                "node_name": node_info.get("name") or node_id,
                                "node_type": node_info.get("type") or "unknown",
                                "state_data": json.dumps(new_vars),
                                "input_data": json.dumps(input_masked),
                                "output_data": json.dumps(output_masked),
                                "latency_ms": latency_ms,
                            }
                        )

                        current_vars = new_vars

                        publish_event(
                            instance_id,
                            "node_update",
                            {
                                "node_id": node_id,
                                "variables": output_masked,
                                "status": "running",
                            },
                        )
            finally:
                await ait.aclose()

            # 执行完毕
            logger.info("[Workflow] Execution completed: instance=%d, total_events=%d", instance_id, event_count)
            # 先 drain 剩余日志，再读 state_data 做 success 终态
            await _drain_flush(flush_queue, flush_task)
            state_data_str = "{}"
            with Session(engine) as session:
                instance = session.get(WorkflowInstance, instance_id)
                if instance:
                    if instance.status == "cancelled":
                        # 末节点刚跑完时用户取消：尊重 cancelled，不发 success
                        session.commit()
                        publish_event(instance_id, "cancelled", {"status": "cancelled"})
                        return
                    state_data_str = instance.state_data
                    _cas(session, "running", status="success")
                    session.commit()

            final_vars = json.loads(state_data_str)
            workflow_output = final_vars.pop("workflow_output", None)
            publish_event(
                instance_id,
                "success",
                {
                    "status": "success",
                    "variables": AiSecurityService.mask_sensitive_dict(final_vars),
                    # output 由 end 节点模板渲染自运行时变量，可能含 PII，同样需脱敏（audit S2：所有 SSE 副本必须脱敏）
                    "output": AiSecurityService.mask_sensitive_dict(workflow_output),
                },
            )

    except Exception as e:
        # 兜底 drain：异常路径也保证已入队的节点日志落库（flush_task 在 try 外创建，此处可达）
        try:
            await _drain_flush(flush_queue, flush_task)
        except Exception:
            logger.error("异常路径 drain flush_task 失败，节点日志可能部分丢失", exc_info=True)
        logger.error("工作流运行异常: %s", e, exc_info=True)
        # 预置默认值：若下方 DB 写入失败走到 except se，error_msg_safe 仍已被赋值，
        # 否则 publish_event 会触发 UnboundLocalError
        error_msg_safe = "执行失败，发生内部错误。"
        try:
            with Session(engine) as session:
                error_msg_safe = str(e) if isinstance(e, ValueError) else "执行失败，发生内部错误。"
                # 仅 running→failed，不覆盖 cancelled（用户在异常发生时取消的情况）
                _cas(session, "running", status="failed", error_message=error_msg_safe)
                session.commit()
        except Exception as se:
            logger.error("记录工作流异常失败: %s", se, exc_info=True)

        publish_event(instance_id, "failed", {"status": "failed", "error": error_msg_safe})
    finally:
        workflow_instance_id_ctx.reset(_inst_ctx_token)
