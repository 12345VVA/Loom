"""
系统任务分发逻辑 (Celery Tasks)
"""
import logging
import time
from datetime import datetime, timedelta
from app.celery_app import celery_app
from app.core.database import Session, engine
from app.modules.task.model.task import TaskInfo, TaskLog
from app.modules.task.service.task_invoker import TaskInvoker

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
            return f"Task {task_id} has no service target"

        log = TaskLog(task_id=task_id, status=1)
        try:
            # 更新最后执行时间
            task.last_execute_time = datetime.utcnow()
            session.add(task)
            session.commit()

            # 执行逻辑
            result = TaskInvoker.invoke(task.service, task.data)
            log.detail = str(result)
            log.status = 1
        except Exception as e:
            log.detail = f"Error: {str(e)}"
            log.status = 0
            print(f"Task {task_id} failed: {e}")
        finally:
            # 记录耗时
            log.consume_time = int((time.time() - start_time) * 1000)
            session.add(log)
            session.commit()
            return f"Task executed with status: {log.status}"


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
