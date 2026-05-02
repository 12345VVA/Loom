"""
系统任务分发逻辑 (Celery Tasks)
"""
import logging
import time
from datetime import datetime, timedelta
from sqlmodel import select
from app.celery_app import celery_app
from app.core.database import Session, engine, transaction
from app.framework.middleware.metrics import record_metric_event
from app.modules.task.model.task import TaskInfo, TaskLog
from app.modules.task.service.task_invoker import TaskInvoker
from app.modules.task.service.task_service import compute_next_run_time, sync_task_schedule_state
from app.modules.notification.service.notification_service import NotificationService

logger = logging.getLogger(__name__)


@celery_app.task(name="task.execute_system_task")
def execute_system_task(task_id: int):
    """
    执行系统任务的全局入口
    """
    start_time = time.time()

    with Session(engine) as session:
        task = session.get(TaskInfo, task_id)
        if not task:
            return f"Task {task_id} not found"

        if not task.service:
            consume_time = int((time.time() - start_time) * 1000)
            _write_task_log(session, task_id, 0, "任务未配置 service", consume_time)
            return f"Task {task_id} has no service target"

        try:
            # 更新最后执行时间
            task.last_execute_time = datetime.utcnow()

            # 执行逻辑
            result = TaskInvoker.invoke(task.service, task.data)
            detail = str(result)
            status = 1
            record_metric_event("task_executed", status="success")
        except Exception as e:
            detail = f"Error: {str(e)}"
            status = 0
            record_metric_event("task_executed", status="failed")
            logger.exception("Task %s failed", task_id)
        finally:
            if task:
                task.next_run_time = compute_next_run_time(task)
                sync_task_schedule_state(task)
                session.add(task)
            consume_time = int((time.time() - start_time) * 1000)
            log = _write_task_log(session, task_id, status, detail, consume_time)
            if task:
                _maybe_send_task_notification(session, task, status, detail, consume_time)
            return f"Task executed with status: {status}"


@celery_app.task(name="task.dispatch_due_tasks")
def dispatch_due_tasks():
    """保守调度器：周期扫描已启用且到期的任务并分发执行。"""
    now = datetime.utcnow()
    dispatched: list[int] = []
    with Session(engine) as session:
        tasks = session.exec(
            select(TaskInfo).where(
                TaskInfo.status == 1,
                (TaskInfo.next_run_time == None) | (TaskInfo.next_run_time <= now),  # noqa: E711
            )
        ).all()
        for task in tasks:
            if task.id is None:
                continue
            if task.next_run_time is None:
                task.next_run_time = compute_next_run_time(task, now)
                session.add(task)
                continue
            task.next_run_time = compute_next_run_time(task, now)
            session.add(task)
            execute_system_task.delay(task.id)
            dispatched.append(task.id)
        session.commit()
    record_metric_event("task_dispatched", count=len(dispatched))
    return {"success": True, "dispatched": dispatched}


def _write_task_log(session: Session, task_id: int, status: int, detail: str, consume_time: int) -> TaskLog:
    log = TaskLog(
        task_id=task_id,
        status=status,
        detail=detail[:2000] if detail else None,
        consume_time=consume_time,
    )
    with transaction(session):
        session.add(log)
    session.refresh(log)
    return log


def _maybe_send_task_notification(session: Session, task: TaskInfo, status_value: int, detail: str, consume_time: int) -> None:
    if not task.notify_enabled:
        return
    timed_out = task.notify_timeout_ms > 0 and consume_time >= task.notify_timeout_ms
    should_notify = (
        (status_value == 1 and task.notify_on_success)
        or (status_value == 0 and task.notify_on_failure)
        or (timed_out and task.notify_on_timeout)
    )
    if not should_notify:
        return
    audience = task.notify_recipients or {"allAdmins": True}
    NotificationService(session).send_task(
        task_name=task.name,
        task_id=task.id,
        status_value=status_value,
        consume_time=consume_time,
        detail=detail,
        audience=audience,
        template_code=task.notify_template_code,
        timeout=timed_out,
    )


@celery_app.task(name="task.clean_expired_logs")
def clean_expired_logs():
    """
    定时清理过期日志
    根据系统参数 logKeep 配置的天数，删除过期的操作日志和登录日志
    """
    from app.modules.base.model.sys import SysLog, SysLoginLog
    from app.modules.base.service.sys_manage_service import LOG_KEEP_PARAM_KEY, DEFAULT_LOG_KEEP_DAYS
    from sqlalchemy import delete

    try:
        with Session(engine) as session:
            # 获取日志保留天数配置
            from app.modules.base.service.sys_manage_service import SysParamService
            param_service = SysParamService(session)
            keep_days_str = param_service.get_value(LOG_KEEP_PARAM_KEY, DEFAULT_LOG_KEEP_DAYS)
            try:
                keep_days = int(keep_days_str)
            except (ValueError, TypeError):
                keep_days = int(DEFAULT_LOG_KEEP_DAYS)

            # 计算删除截止时间
            cutoff_time = datetime.utcnow() - timedelta(days=keep_days)

            # 删除过期的操作日志
            stmt_sys_log = delete(SysLog).where(SysLog.created_at < cutoff_time)
            result_sys_log = session.exec(stmt_sys_log)
            sys_log_count = result_sys_log.rowcount

            # 删除过期的登录日志
            stmt_login_log = delete(SysLoginLog).where(SysLoginLog.created_at < cutoff_time)
            result_login_log = session.exec(stmt_login_log)
            login_log_count = result_login_log.rowcount

            session.commit()

            logger.info(
                f"日志清理完成 - 保留天数: {keep_days}, "
                f"删除操作日志: {sys_log_count}条, 删除登录日志: {login_log_count}条"
            )

            return {
                "success": True,
                "keep_days": keep_days,
                "sys_log_deleted": sys_log_count,
                "login_log_deleted": login_log_count,
                "cutoff_time": cutoff_time.isoformat()
            }
    except Exception as exc:
        logger.error(f"日志清理任务执行失败", exc_info=exc)
        return {
            "success": False,
            "error": str(exc)
        }
