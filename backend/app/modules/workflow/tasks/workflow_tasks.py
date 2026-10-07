"""
工作流 Celery 异步任务入口。
将工作流执行从 Web 进程剥离到独立 Worker，避免进程重启丢失运行中实例。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import time
from typing import Any

# Windows 上 psycopg 异步模式不兼容默认的 ProactorEventLoop，需切换为 SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlmodel import select

import app.modules.workflow.service.workflow_service as _workflow_service  # noqa: F401  冗余保险：compile_graph 入口已确保注册，此处保留双保险以防漏
from app.celery_app import celery_app
from app.core.database import Session, engine
from app.core.logging import workflow_instance_id_ctx
from app.framework.storage import resolve_payload
from app.modules.ai.service.security_service import AiSecurityService
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
from app.modules.workflow.service.artifact_service import persist_workflow_artifacts
from app.modules.workflow.service.checkpointer import get_async_checkpointer
from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.error_format import friendly_error_message
from app.modules.workflow.service.event_bus import publish_event
from app.modules.workflow.service.graph_validate import graph_has_interrupt_nodes, migrate_legacy_tool_nodes
from app.modules.workflow.service.status_flow import cas_transition

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


def apply_start_input_defaults(graph_json: dict, inputs: dict) -> dict:
    """按开始节点声明的默认值补齐工作流输入。

    开始节点的 ``config.inputVariables`` 兼容两种声明：
      - 旧写法纯变量名：``["query"]``
      - 新写法带默认值：``[{"name": "count", "default": 10}]``

    仅当输入缺失、为 None 或为空字符串/纯空白时才回落到默认值；用户显式传入的值一律优先。
    ``graph_json`` 是库中的原始拓扑（config 键为前端 camelCase），因此同时兼容
    ``inputVariables`` / ``input_variables`` 两种键名。
    """
    if not isinstance(inputs, dict) or not isinstance(graph_json, dict):
        return inputs

    start_cfg: dict | None = None
    for node in graph_json.get("nodes") or []:
        if isinstance(node, dict) and node.get("type") == "start":
            start_cfg = node.get("config") or {}
            break
    if not start_cfg:
        return inputs

    declared = start_cfg.get("inputVariables")
    if declared is None:
        declared = start_cfg.get("input_variables")
    if not isinstance(declared, list):
        return inputs

    merged = dict(inputs)
    for item in declared:
        name: str | None = None
        has_default = False
        default: Any = None
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if "default" in item:
                has_default = True
                default = item.get("default")
        if not name or not has_default:
            continue

        current = merged.get(name)
        if current is None or (isinstance(current, str) and not current.strip()):
            merged[name] = default

    return merged


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
                # error 行也会推进 current_node 到失败节点：失败后实例随终态置 failed，
                # current_node 指向失败节点语义正确（顺带修复失败路径的定位 off-by-one）
                inst.current_node = p["node_id"]
                # T8：state_data 超阈值落对象存储 + 存引用，避免状态快照超列宽导致落库失败（实例卡 running）
                state_data, state_data_ref = _maybe_offload(p["state_data"])
                inst.state_data = state_data
                inst.state_data_ref = state_data_ref
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
                # error 行由异常兜底投递（_build_error_log_payload），缺 key 视为成功行（兼容旧调用形态）
                status=p.get("status", "success"),
                error_message=(p.get("error_message") or None),
            )
            session.add(log)
            session.flush()  # 取 log.id 作为下一条 ref_prev 的 base
            prev_log_id = log.id
        session.commit()


def _build_error_log_payload(error: BaseException, nodes_map: dict, current_vars: dict) -> dict | None:
    """构造失败节点的 error 日志 payload；失败节点未知（异常无 node_id）时返回 None。

    与成功行 payload 同构（_persist 会无条件读 state_data/latency_ms 更新实例进度，
    缺 key 会 KeyError 且日志行静默丢失）：
    - state_data 用未脱敏的 current_vars 快照（与成功行一致，input/output 才是脱敏副本）
    - output 为空对象：失败节点没有输出
    """
    node_id = getattr(error, "node_id", None)
    if not node_id:
        return None
    node_info = nodes_map.get(node_id) or {}
    node_names = {nid: (n.get("name") or nid) for nid, n in nodes_map.items()}
    return {
        "node_id": node_id,
        "node_name": node_info.get("name") or node_id,
        "node_type": node_info.get("type") or "unknown",
        "state_data": json.dumps(current_vars),
        "input_data": json.dumps(AiSecurityService.mask_sensitive_dict(current_vars)),
        "output_data": "{}",
        "latency_ms": 0,
        "status": "error",
        "error_message": friendly_error_message(error, node_names),
    }


def _is_cancelled_sync(instance_id: int) -> bool:
    """协作式取消探活：读取 instance.status 是否已被 cancel_instance 置为 cancelled。"""
    with Session(engine) as session:
        inst = session.get(WorkflowInstance, instance_id)
        return bool(inst and inst.status == "cancelled")


def _set_current_node_sync(instance_id: int, node_id: str) -> None:
    """节点开始执行时推进 instance.current_node（WF-P1-6：归因从滞后变即时）。

    CAS status=='running' 防覆盖 paused/cancelled/failed 终态。best-effort：
    失败仅告警，不阻断执行。
    """
    try:
        with Session(engine) as session:
            # running → running（保持运行态，仅推进 current_node），走表驱动 CAS
            cas_transition(session, instance_id, ("running",), "running", extra_values={"current_node": node_id})
            session.commit()
    except Exception:
        logger.warning("工作流实例 %d 推进 current_node=%s 失败", instance_id, node_id, exc_info=True)


async def _flush_worker(instance_id: int, queue: asyncio.Queue, stats: dict) -> None:
    """后台批量落库协程：按批大小或时间间隔 flush，收到 SENTINEL 则处理剩余后退出。

    Queue/Task 均在 async_execute 的 asyncio.run 事件循环内创建与销毁，不跨 Celery prefork
    fork 复用。单消费者保证节点日志 FIFO。

    stats 契约（WF-P2-2）：{"errors": 落库失败批次数, "dropped": 丢弃日志行数}——
    单批落库失败时累加并丢弃该批、继续消费（消费循环永不因落库失败退出），
    由 _drain_flush 收尾汇总告警。杜绝此前「单批失败 → 协程死亡 → 后续批次
    无人消费 + 实例被落库异常误标 failed」的连锁。
    """
    batch: list[dict] = []
    last_flush = time.perf_counter()

    async def _persist_batch() -> None:
        if not batch:
            return
        try:
            await asyncio.to_thread(_persist_node_payloads_sync, instance_id, batch)
        except Exception:
            stats["errors"] += 1
            stats["dropped"] += len(batch)
            logger.error("工作流实例 %d 节点日志批量落库失败，丢弃 %d 条", instance_id, len(batch), exc_info=True)
        finally:
            batch.clear()

    while True:
        timeout = max(0.01, _FLUSH_INTERVAL_SECONDS - (time.perf_counter() - last_flush))
        try:
            item = await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            await _persist_batch()
            last_flush = time.perf_counter()
            continue

        if item is _FLUSH_SENTINEL:
            await _persist_batch()
            return

        batch.append(item)
        if len(batch) >= _FLUSH_BATCH_SIZE:
            await _persist_batch()
            last_flush = time.perf_counter()


async def _drain_flush(queue: asyncio.Queue, task: asyncio.Task, instance_id: int, stats: dict) -> None:
    """收尾：通知 flush_worker 处理剩余 batch 并退出，保证退出前日志已落库。"""
    await queue.put(_FLUSH_SENTINEL)
    try:
        await asyncio.wait_for(task, timeout=_FLUSH_DRAIN_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("工作流 flush_worker 收尾超时，强制取消")
        task.cancel()
    if stats.get("errors"):
        logger.warning(
            "工作流实例 %d flush 收尾汇总：%d 批节点日志落库失败，共丢弃 %d 条",
            instance_id,
            stats["errors"],
            stats.get("dropped", 0),
        )


def _promote_pending_to_running(instance_id: int) -> bool:
    """两段式启动段二：CAS pending→running，执行体真正开跑时调用（async_execute 第一步）。

    rowcount=0 时复查最新状态（commit 已 expire，get 必发新查询）：
    - running → True：eval 侧直建 running 的实例（不经 Celery 队列）与重复 promote；
    - cancelled / failed / 行不存在 → False：排队中被取消、被 sweep/recover 回收、
      被删除——终态与事件已由触发方落定，调用方静默退出，不产生任何执行副作用。
    """
    with Session(engine) as session:
        # 表驱动 CAS（三期B7 / WF-P2-16，下同）
        result_rc = cas_transition(session, instance_id, ("pending",), "running")
        session.commit()
        if result_rc:
            return True
        inst = session.get(WorkflowInstance, instance_id)
        return bool(inst and inst.status == "running")


def _mark_instance_failed(
    instance_id: int, message: str, expected: str | tuple[str, ...] = ("running", "pending")
) -> None:
    """Celery 任务入口兜底：把实例置为 failed 并发布事件（仅当当前状态在 expected 内，避免覆盖 cancelled）。

    用于 execute_workflow 在 asyncio.run 之前就失败的场景（如参数 JSON 解析失败）：
    此时实例仍为 pending/running（两段式下 JSON 解析先于 promote），若不主动写终态，
    需等进程重启由 recover_orphaned_instances 兜底（最长 30 分钟）。
    """
    try:
        expected_statuses = expected if isinstance(expected, tuple) else (expected,)
        with Session(engine) as session:
            rowcount = cas_transition(
                session,
                instance_id,
                expected_statuses,
                "failed",
                extra_values={"error_message": (message or "")[:500]},
            )
            session.commit()
            if rowcount:
                publish_event(instance_id, "failed", {"status": "failed", "error": message, "node_id": None})
                _notify_workflow_failure(instance_id)
    except Exception as se:
        logger.error("记录工作流实例 %d failed 终态失败: %s", instance_id, se, exc_info=True)


def _notify_workflow_failure(instance_id: int) -> None:
    """T6：工作流失败通知（best-effort，异常仅记 warning，不影响终态写入与 SSE 推送）。

    读取实例终态（failed_node_id/error_message/user_id）+ 定义名称，渲染 workflow.failed 模板后投递。
    独立开 session，避免与调用方的 session 生命周期耦合。
    """
    try:
        with Session(engine) as session:
            inst = session.get(WorkflowInstance, instance_id)
            if not inst or not inst.user_id:
                return
            # 副作用门控：试运行/评估实例失败不打扰用户（仅正式实例发通知），结果仍可通过列表/SSE 查看
            if inst.run_type != "production":
                return
            definition = session.get(WorkflowDefinition, inst.definition_id)
            workflow_name = definition.name if definition else None
            from app.modules.notification.service.notification_service import NotificationService

            notification_service = NotificationService(session)
            title, content, level, link_url = notification_service.render_template(
                "workflow.failed",
                {
                    "workflow_name": workflow_name or "未知",
                    "instance_id": inst.id,
                    "node_id": inst.failed_node_id or "未知",
                    "error_message": inst.error_message or "未知错误",
                },
            )
            notification_service.send_business(
                title=title,
                content=content,
                audience={"users": [inst.user_id]},
                source_module="workflow",
                business_key=str(inst.id),
                level=level,
                link_url=link_url,
            )
    except Exception as notify_err:
        logger.warning("工作流失败通知发送异常: %s", notify_err)


@celery_app.task(
    name="workflow.execute",
    bind=True,
    max_retries=0,
    task_time_limit=30 * 60,
)
def execute_workflow(
    self, instance_id: int, definition_id: int, initial_vars_json: str, resume_val_json: str | None = None
):
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
    asyncio.run(async_execute(instance_id, definition_id, initial_vars, resume_val))


@celery_app.task(name="workflow.version.sweep_archived")
def sweep_archived_versions() -> None:
    """周期清理过期归档工作流版本（兜底版本表无限增长，跳过被引用版本）。"""
    from app.modules.workflow.service.workflow_version_service import WorkflowVersionService

    with Session(engine) as session:
        swept = WorkflowVersionService(session).sweep_old_archived()
    if swept:
        logger.info("清理 %d 个过期归档工作流版本", swept)


@celery_app.task(name="workflow.cleanup.sweep")
def sweep_workflow_cleanup() -> dict:
    """周期清理执行日志（SysParam workflowExecutionLogKeepDays，默认 90 天）、终态实例的
    LangGraph checkpoint（workflowCheckpointKeepDays，默认 7 天）与孤儿载荷文件。

    先删日志再回收孤儿：同轮内日志删除后残留的载荷文件即被孤儿回收兜底。
    checkpoint 回收仅 postgres backend 生效（见 sweep_checkpoint_threads）。
    """
    from app.modules.base.service.sys_manage_service import SysParamService
    from app.modules.workflow.service.cleanup_service import WorkflowCleanupService

    with Session(engine) as session:
        keep_days = _int_param(SysParamService(session).get_value("workflowExecutionLogKeepDays", "90"), 90)
        # 单节点测试日志独立短保留（开发期高频、载荷大、追溯价值衰减快）
        test_node_keep_days = _int_param(SysParamService(session).get_value("workflowTestNodeLogKeepDays", "7"), 7)
        service = WorkflowCleanupService(session)
        logs_removed = service.sweep_execution_logs(keep_days=keep_days, test_node_keep_days=test_node_keep_days)
        orphans_removed = service.sweep_orphan_payloads()
        ckpt_keep_days = _int_param(SysParamService(session).get_value("workflowCheckpointKeepDays", "7"), 7)
        checkpoint_threads_removed = service.sweep_checkpoint_threads(keep_days=ckpt_keep_days)
        # 记忆墓碑硬清：统一回收容量淘汰/手动删/definition 级联三种软删来源（设计 §4.4）
        memory_keep_days = _int_param(SysParamService(session).get_value("workflowMemoryTombstoneKeepDays", "90"), 90)
    from app.modules.workflow.service.workflow_memory_service import sweep_memory_tombstones

    memory_tombstones_removed = sweep_memory_tombstones(memory_keep_days)
    return {
        "logsRemoved": logs_removed,
        "orphanPayloadsRemoved": orphans_removed,
        "checkpointThreadsRemoved": checkpoint_threads_removed,
        "memoryTombstonesRemoved": memory_tombstones_removed,
        "keepDays": keep_days,
    }


@celery_app.task(name="workflow.cleanup.sweep_stuck_instances")
def sweep_stuck_instances() -> dict:
    """周期回收假死的 running/pending 实例（checkpoint P1 遗留兜底）。

    worker 挂死/OOM kill 后实例永久滞留 running：删除被拒（需先取消）、无任何周期收尸。
    与启动回收器 recover_orphaned_instances（进程重启场景，30 分钟宽限）互补，本任务覆盖
    「进程未重启但 worker 挂死」的窗口。宽限期经 SysParam workflowStuckInstanceGraceMinutes
    控制（默认 60 分钟，须大于单节点最长合法静默期 600s + 队列积压时长，防误杀慢节点/排队实例）。
    production 实例回收后按模板发失败通知（_notify_workflow_failure 内部按 run_type 门控）。
    """
    from app.modules.base.service.sys_manage_service import SysParamService
    from app.modules.workflow.service.cleanup_service import WorkflowCleanupService

    with Session(engine) as session:
        grace_minutes = _int_param(SysParamService(session).get_value("workflowStuckInstanceGraceMinutes", "60"), 60)
        swept_ids = WorkflowCleanupService(session).sweep_stuck_running_instances(grace_minutes)
    for instance_id in swept_ids:
        _notify_workflow_failure(instance_id)
    if swept_ids:
        logger.info("假死实例回收完成 grace_minutes=%s swept=%d", grace_minutes, len(swept_ids))
    return {"sweptInstances": len(swept_ids), "graceMinutes": grace_minutes}


def _int_param(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _resolve_execution_graph(
    session: Session,
    instance_id: int,
    definition_id: int,
    version_id: int | None,
    graph_json_override: dict | None,
) -> tuple[dict, str] | None:
    """解析工作流拓扑：返回 (graph_json, thread_id)；实例/定义/版本缺失时返回 None。

    版本优先级：graph_json_override（eval 存量 fallback）> version_id > instance.version_id
    > definition.current_version_id。graph_json 现已存版本表（纯版本表模型）。
    """
    instance = session.get(WorkflowInstance, instance_id)
    definition = session.get(WorkflowDefinition, definition_id)
    if not instance or not definition:
        logger.error("工作流执行失败: 找不到实例 %d 或定义 %d", instance_id, definition_id)
        return None
    thread_id = instance.thread_id
    if graph_json_override is not None:
        graph_json = graph_json_override
    else:
        effective_vid = version_id or instance.version_id or definition.current_version_id
        if effective_vid is None:
            logger.error("工作流执行失败: 实例 %d 无可用版本（未发布？）", instance_id)
            return None
        version = session.get(WorkflowDefinitionVersion, effective_vid)
        if not version:
            logger.error("工作流执行失败: 版本 %d 不存在", effective_vid)
            return None
        graph_json = json.loads(version.graph_json)
    # 三期B7（WF-P2-10）：执行入口统一迁移 deprecated tool → tool_executor
    # （override（eval 快照）与版本两分支都要过，eval 快照可能是旧图）
    graph_json = migrate_legacy_tool_nodes(graph_json)
    return graph_json, thread_id


async def async_execute(
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

    resume_val 非空（恢复路径）时 initial_vars 不参与图执行——状态自 checkpoint 经
    Command(resume=…) 恢复；该参数仅作为异常兜底路径 current_vars 的初值，供失败节点日志构建
    （核实清单 WF-P2-18）。
    """
    from langgraph.types import Command

    from app.core.config import settings

    node_timeout = settings.WORKFLOW_NODE_TIMEOUT

    def _cas(session, expected_status: str, **values) -> int:
        """对实例做条件更新（仅当当前状态等于 expected_status），返回受影响行数。
        避免执行循环的终态写入覆盖已被 cancel_instance 写入的 cancelled 状态。
        三期B7（WF-P2-16）：迁移合法性由 status_flow 表校验。
        """
        to_status = values.pop("status", expected_status)
        return cas_transition(session, instance_id, (expected_status,), to_status, extra_values=values)

    # T4：批量落库后台协程（在 try 外创建，使外层 except 兜底可 drain；flush_worker 只用 engine，不依赖 checkpointer）
    flush_queue: asyncio.Queue = asyncio.Queue()
    # 创建在 try 之外（与 flush_queue 同层）：编译前异常的兜底路径也可安全引用
    flush_stats = {"errors": 0, "dropped": 0}
    flush_task = asyncio.create_task(_flush_worker(instance_id, flush_queue, flush_stats))

    # 兜底异常路径引用的执行态：编译前异常（拓扑解析/编译失败）时事件循环未启动，
    # 预初始化避免 UnboundLocalError；正常路径由事件循环内赋值覆盖
    nodes_map: dict = {}
    current_vars: dict = initial_vars

    # 设置 contextvar：本次实例的所有 LLM 调用（节点执行）按 instance 打标，
    # 供 workflow_eval 按 instance 精确聚合 token/cost（runtime_service._log_call 读取）
    _inst_ctx_token = workflow_instance_id_ctx.set(instance_id)

    try:
        # 0. 两段式启动段二：pending→running。eval 直建 running 的实例经复查容错放行；
        # 排队中被取消/回收/删除的实例在此静默退出（终态与事件已由触发方落定）。
        if not _promote_pending_to_running(instance_id):
            logger.info("[Workflow] 实例 %d 已非可执行状态（排队中被取消或回收），跳过执行", instance_id)
            return

        # 1. 编译拓扑：解析 graph_json + thread_id（实例/定义/版本缺失则提前退出）
        with Session(engine) as session:
            resolved = _resolve_execution_graph(session, instance_id, definition_id, version_id, graph_json_override)
            if resolved is None:
                return
            graph_json, thread_id = resolved
        logger.info(
            "[Workflow] Compiling graph: instance=%d, nodes=%s, edges=%s",
            instance_id,
            [n.get("id") for n in graph_json.get("nodes", [])],
            [(e.get("source"), e.get("target"), e.get("type")) for e in graph_json.get("edges", [])],
        )
        # B：按开始节点声明的默认值补齐输入（未传/空串时回落到默认值，用户显式值优先）。
        # 放在编译前——默认值随初始 state 进入 variables，正式运行/试运行/评估三条路径共用。
        initial_vars = apply_start_input_defaults(graph_json, initial_vars)

        graph = WorkflowCompiler.compile_graph(graph_json)

        # P0：无中断节点且非恢复路径的图跳过 checkpointer——LangGraph 以内存态完成 astream，
        # 省去每步全量快照落库（variables 累积 merge 下 checkpoint_blobs 为 O(N²) 写放大）。
        # resume 走 Command(resume=...) 硬依赖断点，强制挂载；开关见
        # WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT（kill-switch）。
        use_checkpointer = resume_val is not None or (
            settings.WORKFLOW_CHECKPOINT_SKIP_WITHOUT_INTERRUPT and graph_has_interrupt_nodes(graph_json)
        )
        cm = get_async_checkpointer() if use_checkpointer else contextlib.nullcontext()
        async with cm as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer) if use_checkpointer else graph.compile()
            logger.info(
                "[Workflow] Graph compiled successfully, instance=%d, checkpointer=%s", instance_id, use_checkpointer
            )

            # 三期B7（WF-P2-24）：recursion_limit settings 化（原硬编码 100）
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.WORKFLOW_RECURSION_LIMIT,
            }

            # 2. 区分启动与恢复
            if resume_val is not None:
                events = compiled.astream(Command(resume=resume_val), config=config, stream_mode=["updates", "custom"])
            else:
                initial_state = {"variables": initial_vars, "current_node": "start"}
                events = compiled.astream(initial_state, config=config, stream_mode=["updates", "custom"])

            last_step_time = time.perf_counter()
            current_vars = initial_vars
            event_count = 0
            # node_done custom 事件 → 同节点 updates 事件的 latency 关联
            # （WF-P2-15：真实节点耗时，缺失时回退事件间隔计算）
            _node_latency: dict[str, int] = {}

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
                        await _drain_flush(flush_queue, flush_task, instance_id, flush_stats)
                        timeout_node_id = None
                        with Session(engine) as session:
                            inst = session.get(WorkflowInstance, instance_id)
                            if inst:
                                timeout_node_id = inst.current_node
                            # current_node 自 node_start 起由执行开始时写入（WF-P1-6），
                            # 语义为「正在执行的节点」——超时归因从滞后的「最后完成节点」
                            # 变为即时的「当前执行节点」
                            timeout_node_name = (
                                ((nodes_map.get(timeout_node_id, {}) or {}).get("name") or timeout_node_id)
                                if timeout_node_id
                                else None
                            )
                            timeout_msg = (
                                f"节点执行超时（{node_timeout}秒），当前执行节点：「{timeout_node_name}」"
                                if timeout_node_name
                                else f"节点执行超时（{node_timeout}秒）"
                            )
                            _cas(
                                session,
                                "running",
                                status="failed",
                                error_message=timeout_msg,
                                failed_node_id=timeout_node_id,
                            )
                            session.commit()
                        logger.warning("[Workflow] 节点执行超时 instance=%d (%ds)", instance_id, node_timeout)
                        publish_event(
                            instance_id,
                            "failed",
                            {"status": "failed", "error": timeout_msg, "node_id": timeout_node_id},
                        )
                        _notify_workflow_failure(instance_id)
                        return

                    # 双形态适配（WF-P1-6）：langgraph 1.2.1 list 模式恒产 (mode, payload) 元组。
                    # 严禁裸 `mode, payload = event`——dict 会按键解包造成静默错位，必须 isinstance 判别。
                    if isinstance(event, tuple) and len(event) == 2:
                        mode, payload = event
                    else:
                        logger.error("[Workflow] 意外的事件形态: %r", event)
                        continue

                    if mode == "custom":
                        # node_runner 发出的节点级执行事件：node_start（画布即时高亮 +
                        # DB current_node 即时归因）/ node_done（真实耗时关联）。
                        if not isinstance(payload, dict):
                            continue
                        etype = payload.get("type")
                        if etype == "node_start":
                            nid = payload.get("node_id")
                            if nid:
                                # 先写 DB 再广播，保证前端收到高亮事件时 DB 归因已就绪；
                                # 串行等待保证 N 与 N+1 的写入不乱序
                                await asyncio.to_thread(_set_current_node_sync, instance_id, nid)
                            publish_event(instance_id, "node_start", payload)
                        elif etype == "node_done":
                            nid = payload.get("node_id")
                            lat = payload.get("latency_ms")
                            if nid and isinstance(lat, int):
                                _node_latency[nid] = lat
                            publish_event(instance_id, "node_done", payload)
                        else:
                            logger.debug("[Workflow] 忽略未知 custom 事件: %r", payload)
                        continue

                    # ── mode == "updates"：节点完成事件，现有处理逻辑 ──
                    for node_id, node_output in payload.items():
                        event_count += 1
                        current_time = time.perf_counter()
                        # 真实节点耗时（node_done custom 事件携带）；缺失时回退事件间隔。
                        # 无论是否命中都必须刷新 last_step_time，否则回退路径会算出虚高间隔
                        latency_ms = _node_latency.pop(node_id, None)
                        if latency_ms is None:
                            latency_ms = int((current_time - last_step_time) * 1000)
                        last_step_time = current_time

                        if node_id == "__interrupt__":
                            # 中断前先把已入队的日志落库，再写 paused 终态
                            await _drain_flush(flush_queue, flush_task, instance_id, flush_stats)
                            if not use_checkpointer:
                                # 防呆：图声称无中断节点却收到 __interrupt__（如未来新增中断节点类型
                                # 未纳入 INTERRUPT_NODE_TYPES），无 checkpointer 时写 paused 将永远
                                # 无法 resume（制造假死实例），按 failed 收尾暴露问题
                                err_msg = (
                                    "收到中断事件但本次执行未挂载断点（checkpointer），无法进入可恢复的暂停态；"
                                    "请检查图中断节点类型是否已纳入 INTERRUPT_NODE_TYPES"
                                )
                                with Session(engine) as session:
                                    _cas(session, "running", status="failed", error_message=err_msg)
                                    session.commit()
                                logger.error("[Workflow] %s instance=%d", err_msg, instance_id)
                                publish_event(instance_id, "failed", {"status": "failed", "error": err_msg})
                                _notify_workflow_failure(instance_id)
                                return
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
                            await _drain_flush(flush_queue, flush_task, instance_id, flush_stats)
                            logger.info("[Workflow] 实例 %d 已取消，停止执行", instance_id)
                            publish_event(instance_id, "cancelled", {"status": "cancelled"})
                            return

                        node_info = nodes_map.get(node_id, {})
                        # 三期B5（WF-P1-3）：节点返回值即将改为 applied delta（键级增量），
                        # 此处把增量键级累加进全量视图；对全量快照形态该合并幂等
                        # （{**old, **full} == full），delta 化前后行为一致。
                        # state_data 落库口径保持全量快照（展示/续跑需要），output_data
                        # 保持本节点原始返回（delta 化后即「本节点产出」的更准确语义）。
                        merged_vars = {**current_vars, **new_vars}
                        # T5：脱敏 + 序列化在入队前完成，保证落库 payload 已脱敏（不削弱 audit S2）。
                        # 脱敏副本同时用于 SSE 推送，避免重复脱敏。
                        input_masked = AiSecurityService.mask_sensitive_dict(current_vars)
                        output_masked = AiSecurityService.mask_sensitive_dict(new_vars)
                        await flush_queue.put(
                            {
                                "node_id": node_id,
                                "node_name": node_info.get("name") or node_id,
                                "node_type": node_info.get("type") or "unknown",
                                "state_data": json.dumps(merged_vars),
                                "input_data": json.dumps(input_masked),
                                "output_data": json.dumps(output_masked),
                                "latency_ms": latency_ms,
                            }
                        )

                        current_vars = merged_vars

                        publish_event(
                            instance_id,
                            "node_update",
                            {
                                "node_id": node_id,
                                # 产物/变量全文不再随 SSE 推送（前端零消费，节点状态由 /logs 还原）；
                                # output_masked 仍用于下方日志落库
                                "status": "running",
                            },
                        )
            finally:
                await ait.aclose()

            # 执行完毕
            logger.info("[Workflow] Execution completed: instance=%d, total_events=%d", instance_id, event_count)
            # 先 drain 剩余日志，再读 state_data 做 success 终态
            await _drain_flush(flush_queue, flush_task, instance_id, flush_stats)
            state_data_str = "{}"
            inst_definition_id: int | None = None
            inst_version_id: int | None = None
            inst_user_id: int | None = None
            with Session(engine) as session:
                instance = session.get(WorkflowInstance, instance_id)
                if instance:
                    if instance.status == "cancelled":
                        # 末节点刚跑完时用户取消：尊重 cancelled，不发 success
                        session.commit()
                        publish_event(instance_id, "cancelled", {"status": "cancelled"})
                        return
                    # T8：state_data 超阈值时以 storage ref 还原全量快照再做 success 终态
                    state_data_str = resolve_payload(instance.state_data, instance.state_data_ref) or "{}"
                    inst_definition_id = instance.definition_id
                    inst_version_id = instance.version_id
                    inst_user_id = instance.user_id
                    cas_rc = _cas(session, "running", status="success")
                    session.commit()
                    if cas_rc == 0:
                        # CAS 未命中：get 之后、CAS 之前的极小窗口内状态被并发改走——
                        # 以 DB 最新状态收尾，不发 success 不落产物（核实清单 WF-P2-20）
                        session.expire(instance)
                        latest_status = instance.status
                        if latest_status == "cancelled":
                            publish_event(instance_id, "cancelled", {"status": "cancelled"})
                        else:
                            logger.warning(
                                "[Workflow] 实例 %d success 收尾时状态已变为 %s，跳过 success 广播",
                                instance_id,
                                latest_status,
                            )
                        return

            final_vars = json.loads(state_data_str)
            workflow_output = final_vars.pop("workflow_output", None)
            # 产物落地（best-effort）：在 success SSE 推送前执行，前端收到事件后打开产物抽屉即可查询
            if inst_definition_id is not None:
                persist_workflow_artifacts(
                    instance_id, inst_definition_id, inst_version_id, inst_user_id, None, workflow_output
                )
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
        logger.error("工作流运行异常: %s", e, exc_info=True)
        # failed_node_id 来自 NodeExecutionError（业务异常精确到节点）；超时等无则留空。
        failed_node_id = getattr(e, "node_id", None)
        node_names = {nid: (n.get("name") or nid) for nid, n in nodes_map.items()}
        # 异常分类折叠为可读消息（节点名 + 原因），替代此前"非 ValueError 一律内部错误"的兜底；
        # friendly_error_message 自身不抛（内部已防御），error_msg_safe 必被赋值
        error_msg_safe = friendly_error_message(e, node_names)
        # 失败节点写入 status=error 的日志行（此前失败节点无日志记录，时间线上缺位）。
        # 必须先 put 再 drain——_drain_flush 送出 SENTINEL 后 flush_worker 直接退出
        err_payload = _build_error_log_payload(e, nodes_map, current_vars)
        if err_payload is not None:
            try:
                await flush_queue.put(err_payload)
            except Exception:
                logger.error("失败节点日志入队失败，该行日志丢失", exc_info=True)
        # 兜底 drain：异常路径也保证已入队的节点日志（含 error 行）落库
        try:
            await _drain_flush(flush_queue, flush_task, instance_id, flush_stats)
        except Exception:
            logger.error("异常路径 drain flush_task 失败，节点日志可能部分丢失", exc_info=True)
        try:
            with Session(engine) as session:
                # 仅 running→failed，不覆盖 cancelled（用户在异常发生时取消的情况）
                _cas(session, "running", status="failed", error_message=error_msg_safe, failed_node_id=failed_node_id)
                session.commit()
        except Exception as se:
            logger.error("记录工作流异常失败: %s", se, exc_info=True)

        publish_event(
            instance_id,
            "failed",
            {"status": "failed", "error": error_msg_safe, "node_id": failed_node_id},
        )
        _notify_workflow_failure(instance_id)
    finally:
        workflow_instance_id_ctx.reset(_inst_ctx_token)
