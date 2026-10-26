"""
Celery 应用配置
"""

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import (
    before_task_publish,
    setup_logging,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
)
from kombu import Queue

from app.core.config import settings
from app.core.logging import (
    configure_logging,
    request_id_ctx,
    workflow_instance_id_ctx,
)
from app.modules.ai.constants import AI_TASK_QUEUES

logger = logging.getLogger("app.exceptions")


@setup_logging.connect
def setup_celery_logging(**kwargs):
    configure_logging(
        log_level=settings.effective_log_level,
        log_dir=settings.LOG_DIR,
        retention_days=settings.LOG_RETENTION_DAYS,
        file_prefix="celery",
    )


@task_failure.connect
def _log_task_failure(sender=None, task_id=None, exc=None, **kwargs):
    """任务失败规范化记录：celery 自带日志格式不统一，统一走应用日志出口。

    exc_info 传异常实例，由 ConsoleFormatter 完成框架帧过滤与异常组展开。
    """
    logger.error(
        "Celery 任务失败: %s[%s]",
        getattr(sender, "name", "?"),
        task_id,
        exc_info=exc,
    )


@task_retry.connect
def _log_task_retry(sender=None, task_id=None, reason=None, **kwargs):
    """任务重试记录：重试是失败的前奏，无栈也要留痕（原因含在 reason 里）。"""
    logger.warning(
        "Celery 任务重试: %s[%s] reason=%s",
        getattr(sender, "name", "?"),
        task_id,
        reason,
    )


# --- 日志上下文跨进程串联：HTTP 请求派发的任务在 worker 侧继承 request_id ---

_TASK_CONTEXT_HEADER = "loom_log_context"
# task.request.id → (contextvar, token) 列表；prerun/postrun 在同一 worker 线程顺序执行
_TASK_CONTEXT_TOKENS: dict[str, list] = {}


@before_task_publish.connect
def _inject_log_context(headers=None, **kwargs):
    """派发侧：把当前请求/工作流日志上下文随消息头带出。"""
    if headers is None:
        return
    context: dict = {}
    if request_id_ctx.get():
        context["request_id"] = request_id_ctx.get()
    if workflow_instance_id_ctx.get() is not None:
        context["workflow_instance_id"] = workflow_instance_id_ctx.get()
    if context:
        headers[_TASK_CONTEXT_HEADER] = context


@task_prerun.connect
def _restore_log_context(task=None, **kwargs):
    """worker 侧：任务开始前恢复派发时携带的日志上下文。

    无来源上下文（beat 定时任务、外部直投）时兜底生成任务级追踪号
    ``celery:{task_id}``，worker 日志可按任务实例检索。
    """
    request = getattr(task, "request", None) if task is not None else None
    run_id = getattr(request, "id", None)
    if run_id:
        # 清同 id 残留（postrun 因异常路径未执行的兜底）：残留 contextvar 必须
        # 一并复位，否则旧值挂在 worker 进程上污染后续任务的日志
        stale_tokens = _TASK_CONTEXT_TOKENS.pop(run_id, None)
        if stale_tokens:
            for var, token in reversed(stale_tokens):
                var.reset(token)
    context = (getattr(request, "headers", None) or {}).get(_TASK_CONTEXT_HEADER)
    tokens: list = []
    if context:
        if context.get("request_id"):
            tokens.append((request_id_ctx, request_id_ctx.set(context["request_id"])))
        if context.get("workflow_instance_id") is not None:
            tokens.append((workflow_instance_id_ctx, workflow_instance_id_ctx.set(context["workflow_instance_id"])))
    elif run_id:
        tokens.append((request_id_ctx, request_id_ctx.set(f"celery:{run_id}")))
    if tokens and run_id:
        _TASK_CONTEXT_TOKENS[run_id] = tokens


@task_postrun.connect
def _clear_log_context(task=None, **kwargs):
    """worker 侧：任务结束后清理 contextvar（worker 进程复用，避免串扰下一个任务）。"""
    request = getattr(task, "request", None) if task is not None else None
    run_id = getattr(request, "id", None)
    tokens = _TASK_CONTEXT_TOKENS.pop(run_id, None) if run_id else None
    if tokens:
        for var, token in reversed(tokens):
            var.reset(token)


celery_app = Celery(
    "loom",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.modules.task.tasks.system_tasks",
        "app.modules.ai.tasks.generation_tasks",
        "app.modules.workflow.tasks.workflow_tasks",
        "app.modules.workflow_eval.tasks.eval_tasks",
        "app.modules.media.tasks.mirror_tasks",
        "app.modules.media.tasks.ingest_tasks",
        "app.modules.agent.tasks.approval_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30分钟超时
    # 任务执行完成后才 ACK（P1-5）：worker 进程级死亡/OOM kill 时任务会被重新投递，
    # 避免静默丢失。配合 reject_on_worker_lost 在 worker 异常退出时拒绝消息重回队列。
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # 软超时 25 分钟（早于 30 分钟硬超时），触发 SoftTimeLimitExceeded 让任务有机会
    # 优雅收尾（写终态、释放锁、发通知），避免硬超时直接 SIGKILL 残留运行态。
    task_soft_time_limit=25 * 60,
    task_queues=(
        Queue("celery"),
        Queue("default"),
        Queue("workflow"),
        Queue("workflow.eval"),  # T9：批量评估独立队列，生产用 -Q workflow.eval 独占 worker，避免饿死正式工作流
        Queue("media.mirror"),  # WFI-3b：媒体产物 TOS 镜像低优先级队列（可并入 default worker 或独立部署）
        Queue("agent.approval"),  # E4：HITL 审批过期巡检（低频周期任务，可并入 default worker）
        *(Queue(queue_name) for queue_name in AI_TASK_QUEUES),
    ),
    task_routes={
        "workflow.execute": {"queue": "workflow"},
        "workflow.eval.run": {"queue": "workflow.eval"},
        "workflow.eval.sweep_timeouts": {"queue": "default"},
        "workflow.version.sweep_archived": {"queue": "default"},
        "workflow.cleanup.sweep": {"queue": "default"},
        "media.mirror_asset": {"queue": "media.mirror"},
        "media.ingest_ai_task": {"queue": "default"},
        "media.ingest.sweep_uningested": {"queue": "default"},
        "ai.execute_generation_task": {"queue": "ai.chat"},
        "ai.clean_expired_governance_data": {"queue": "default"},
        # 系统任务统一走 default 队列，避免落到匿名 celery 队列造成分流混乱
        "task.dispatch_due_tasks": {"queue": "default"},
        "task.execute_system_task": {"queue": "default"},
        "task.clean_expired_logs": {"queue": "default"},
        # E4 HITL 审批巡检（设计附录 task-celery 对齐：agent.approval 队列）
        "agent.approval.sweep_expiry": {"queue": "agent.approval"},
    },
)

# Celery Beat 定时任务配置
celery_app.conf.beat_schedule = {
    # 每分钟扫描启用且到期的数据库任务
    "dispatch-due-system-tasks": {
        "task": "task.dispatch_due_tasks",
        "schedule": 60.0,
    },
    # 每天凌晨2点清理过期日志
    "clean-expired-logs-daily": {
        "task": "task.clean_expired_logs",
        "schedule": crontab(hour=2, minute=0),
    },
    "clean-expired-ai-governance-data-daily": {
        "task": "ai.clean_expired_governance_data",
        "schedule": crontab(hour=3, minute=0),
    },
    # 每 15 分钟巡检超时未终结的评估运行（兜底 worker 进程级死亡/OOM kill）
    "sweep-timed-out-eval-runs": {
        "task": "workflow.eval.sweep_timeouts",
        "schedule": 900.0,
    },
    # 每 15 分钟巡检假死的 running/pending 工作流实例（兜底 worker 挂死；宽限期 SysParam
    # workflowStuckInstanceGraceMinutes 默认 60 分钟，须大于单节点最长合法静默期 600s）
    "sweep-stuck-workflow-instances": {
        "task": "workflow.cleanup.sweep_stuck_instances",
        "schedule": 900.0,
    },
    # 每天凌晨 4 点清理过期归档工作流版本（兜底版本表无限增长，跳过被引用版本）
    "sweep-archived-versions": {
        "task": "workflow.version.sweep_archived",
        "schedule": crontab(hour=4, minute=0),
    },
    # 每天凌晨 4 点半清理工作流执行日志与孤儿载荷（与 2/3/4 点任务错峰）
    "sweep-workflow-cleanup-daily": {
        "task": "workflow.cleanup.sweep",
        "schedule": crontab(hour=4, minute=30),
    },
    # 每小时补偿扫描「success 但从未落资产」的 AI 任务（兜底媒体转存派发丢失）
    "sweep-uningested-ai-media-ingest": {
        "task": "media.ingest.sweep_uningested",
        "schedule": 3600.0,
    },
    # 每分钟巡检 HITL 审批：pending 过期（SLA 默认 7 天）→ expired + 组终局触发恢复；
    # executing 租约残留检测与 args 保留期清理同任务（E4，条件更新幂等，多 worker 安全）
    "sweep-agent-approval-expiry": {
        "task": "agent.approval.sweep_expiry",
        "schedule": 60.0,
        "options": {"queue": "agent.approval"},
    },
}
