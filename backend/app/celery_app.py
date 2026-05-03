"""
Celery 应用配置
"""
from celery import Celery
from app.core.config import settings
from celery.schedules import crontab

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
}
