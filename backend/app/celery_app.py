"""
Celery 应用配置
"""
from celery import Celery
from celery.signals import setup_logging
from app.core.config import settings
from app.core.logging import configure_logging
from celery.schedules import crontab
from kombu import Queue

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
        *(Queue(queue_name) for queue_name in AI_TASK_QUEUES),
    ),
    task_routes={
        "ai.execute_generation_task": {"queue": "ai.chat"},
        "ai.clean_expired_governance_data": {"queue": "default"},
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
}
