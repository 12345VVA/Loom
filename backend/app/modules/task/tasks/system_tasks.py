"""
系统任务分发逻辑 (Celery Tasks)
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.celery_app import celery_app
from app.core.database import Session, engine, transaction
from app.framework.middleware.metrics import record_metric_event
from app.modules.notification.service.notification_service import NotificationService
from app.modules.task.model.task import TaskInfo, TaskLog
from app.modules.base.service.cache_service import cache_delete
from app.modules.task.service.task_invoker import TaskInvoker
from app.modules.task.service.task_service import compute_next_run_time, sync_task_schedule_state

logger = logging.getLogger(__name__)

# 派发任务分布式锁配置（P0-16）
_DISPATCH_LOCK_KEY = "loom:task:dispatch:lock"
_DISPATCH_LOCK_TTL = 60  # 秒，覆盖单次 beat 周期 60s，防多 worker 重复派发

# 释放锁 Lua 脚本（P1-B1）：原子校验 value 后删除，避免误删其他 worker 的锁
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


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
            task.last_execute_time = datetime.now(timezone.utc)

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
            # 释放 once() 防重放锁：任务执行完毕（无论成功失败）立即清除，
            # 使快速完成的任务可被立即重试，而非等 5 分钟 TTL
            try:
                cache_delete(f"task:once:{task_id}")
            except Exception:
                logger.debug("清理 task:once 防重放锁失败", exc_info=True)
            if task:
                task.next_run_time = compute_next_run_time(task)
                sync_task_schedule_state(task)
                session.add(task)
            consume_time = int((time.time() - start_time) * 1000)
            _write_task_log(session, task_id, status, detail, consume_time)
            if task:
                _maybe_send_task_notification(session, task, status, detail, consume_time)

        return f"Task executed with status: {status}"


@celery_app.task(name="task.dispatch_due_tasks")
def dispatch_due_tasks():
    """保守调度器：周期扫描已启用且到期的任务并分发执行。

    多 worker 环境下用 Redis SETNX 抢占锁，确保同一 beat 周期内只有一个 worker
    执行派发，避免重复 .delay() 调用（P0-16）。Redis 不可用时（如本地开发）
    退化为单进程执行，不阻断派发。

    锁 value 使用唯一 token，释放时通过 Lua 脚本原子校验后删除（P1-B1），
    防止 worker A 持锁超过 TTL 后误删 worker B 抢到的新锁。
    """
    from app.core.redis import redis_client

    lock_token: str | None = None
    try:
        lock_token = str(uuid.uuid4())
        acquired = redis_client.set(_DISPATCH_LOCK_KEY, lock_token, nx=True, ex=_DISPATCH_LOCK_TTL)
    except Exception:
        # Redis 不可用：本地开发或单 worker 场景，降级放行
        logger.warning("dispatch_due_tasks Redis 锁不可用，降级为无锁派发", exc_info=True)
        lock_token = None  # 降级路径未实际获取锁，finally 中跳过释放
        acquired = True

    if not acquired:
        logger.debug("dispatch_due_tasks 已被其他 worker 抢占，跳过本次派发")
        return {"success": True, "dispatched": [], "skipped": "lock_contended"}

    try:
        now = datetime.now(timezone.utc)
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
    finally:
        # 主动释放锁，避免等待 TTL 过期才进入下一周期。
        # 仅当持有锁 token 时才尝试释放，降级路径（lock_token=None）跳过。
        # 用 Lua 脚本原子校验 value 后删除，避免误删其他 worker 的锁。
        if lock_token is not None:
            try:
                redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, _DISPATCH_LOCK_KEY, lock_token)
            except Exception:
                logger.debug("释放 dispatch 锁失败（Redis 不可用），等待 TTL 过期", exc_info=True)


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


def _maybe_send_task_notification(
    session: Session, task: TaskInfo, status_value: int, detail: str, consume_time: int
) -> None:
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
    from sqlalchemy import delete

    from app.modules.base.model.sys import SysLog, SysLoginLog
    from app.modules.base.service.sys_manage_service import DEFAULT_LOG_KEEP_DAYS, LOG_KEEP_PARAM_KEY

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
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=keep_days)

            # 删除过期的操作日志
            stmt_sys_log = delete(SysLog).where(SysLog.created_at < cutoff_time)
            result_sys_log = session.exec(stmt_sys_log)
            sys_log_count = result_sys_log.rowcount

            # 删除过期的登录日志
            stmt_login_log = delete(SysLoginLog).where(SysLoginLog.created_at < cutoff_time)
            result_login_log = session.exec(stmt_login_log)
            login_log_count = result_login_log.rowcount

            # 删除过期的任务执行日志
            stmt_task_log = delete(TaskLog).where(TaskLog.created_at < cutoff_time)
            result_task_log = session.exec(stmt_task_log)
            task_log_count = result_task_log.rowcount

            session.commit()

            logger.info(
                f"日志清理完成 - 保留天数: {keep_days}, "
                f"删除操作日志: {sys_log_count}条, 删除登录日志: {login_log_count}条, "
                f"删除任务日志: {task_log_count}条"
            )

            return {
                "success": True,
                "keep_days": keep_days,
                "sys_log_deleted": sys_log_count,
                "login_log_deleted": login_log_count,
                "task_log_deleted": task_log_count,
                "cutoff_time": cutoff_time.isoformat(),
            }
    except Exception as exc:
        logger.error("日志清理任务执行失败", exc_info=exc)
        return {"success": False, "error": str(exc)}
