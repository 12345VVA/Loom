"""
Celery 应用配置
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
from kombu import Queue

from app.core.config import settings
from app.core.logging import configure_logging

AI_TASK_QUEUES = ("ai.chat", "ai.image", "ai.embedding", "ai.rerank", "ai.audio", "ai.video")


@setup_logging.connect
def setup_celery_logging(**kwargs):
    configure_logging(
        log_level=settings.effective_log_level,
        log_dir=settings.LOG_DIR,
        retention_days=settings.LOG_RETENTION_DAYS,
        file_prefix="celery",
    )


celery_app = Celery(
    "loom",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.modules.task.tasks.system_tasks",
        "app.modules.ai.tasks.generation_tasks",
        "app.modules.workflow.tasks.workflow_tasks",
        "app.modules.workflow_eval.tasks.eval_tasks",
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
    task_queues=(
        Queue("celery"),
        Queue("default"),
        Queue("workflow"),
        Queue("workflow.eval"),  # T9：批量评估独立队列，生产用 -Q workflow.eval 独占 worker，避免饿死正式工作流
        *(Queue(queue_name) for queue_name in AI_TASK_QUEUES),
    ),
    task_routes={
        "workflow.execute": {"queue": "workflow"},
        "workflow.eval.run": {"queue": "workflow.eval"},
        "workflow.eval.sweep_timeouts": {"queue": "default"},
        "ai.execute_generation_task": {"queue": "ai.chat"},
        "ai.clean_expired_governance_data": {"queue": "default"},
        # 系统任务统一走 default 队列，避免落到匿名 celery 队列造成分流混乱
        "task.dispatch_due_tasks": {"queue": "default"},
        "task.execute_system_task": {"queue": "default"},
        "task.clean_expired_logs": {"queue": "default"},
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
}
