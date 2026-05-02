"""
系统定时任务服务
"""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery
from app.modules.base.model.auth import PageResult
from app.modules.task.model.task import (
    TaskInfo,
    TaskInfoCreateRequest,
    TaskInfoRead,
    TaskInfoUpdateRequest,
    TaskLog,
    TaskLogRead,
)
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.cache_service import CacheNamespace


TASK_SCHEDULE_CACHE = CacheNamespace("task:schedule", default_ttl_seconds=24 * 60 * 60)


class TaskInfoService(BaseAdminCrudService):
    """系统定时任务服务"""

    def __init__(self, session: Session):
        super().__init__(session, TaskInfo)

    def _after_add(self, entity: TaskInfo, payload: Any = None) -> None:
        sync_task_schedule_state(entity)

    def _after_update(self, entity: TaskInfo, payload: Any = None) -> None:
        sync_task_schedule_state(entity)

    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
        for row in list(self.session.exec(select(TaskInfo).where(TaskInfo.id.in_(ids))).all()):
            if row.id is not None:
                clear_task_schedule_state(row.id)
        return ids

    def log(self, query: CrudQuery) -> PageResult[dict]:
        """查询任务日志"""
        page = query.page or 1
        page_size = query.size or 10
        id_val = query.params.get("id")
        status_val = query.params.get("status")

        # 联表查询：获取日志和任务名称
        statement = select(TaskLog, TaskInfo.name.label("task_name")).join(
            TaskInfo, TaskLog.task_id == TaskInfo.id
        )
        if id_val:
            statement = statement.where(TaskLog.task_id == id_val)
        if status_val is not None:
            statement = statement.where(TaskLog.status == status_val)
        
        statement = statement.order_by(TaskLog.created_at.desc())
        
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        results = self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()
        
        data_list = []
        for log_row, task_name in results:
            # 使用基类转换逻辑
            item_data = self._row_to_dict(log_row)
            item_data["task_name"] = task_name
            data_list.append(self._finalize_data(item_data))

        return PageResult(items=data_list, total=total, page=page, page_size=page_size)

    async def start(self, id: int):
        """启动任务"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        row.status = 1
        row.next_run_time = compute_next_run_time(row)
        self.session.add(row)
        self.session.commit()
        sync_task_schedule_state(row)
        return {"success": True}

    async def stop(self, id: int):
        """停止任务"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        row.status = 0
        row.next_run_time = None
        self.session.add(row)
        self.session.commit()
        clear_task_schedule_state(id)
        return {"success": True}

    async def once(self, id: int):
        """立即执行一次"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 异步触发 Celery 任务
        from app.modules.task.tasks.system_tasks import execute_system_task
        execute_system_task.delay(id)
        
        return {"success": True}


def compute_next_run_time(task: TaskInfo, now: datetime | None = None) -> datetime | None:
    """计算保守调度器的下次运行时间。"""
    if task.status != 1:
        return None
    now = now or datetime.utcnow()
    if task.start_date and task.start_date > now:
        return task.start_date
    if task.task_type == 1 and task.every:
        return now + timedelta(milliseconds=task.every)
    if task.task_type == 0:
        return compute_next_cron_run_time(task.cron, now)
    return now


def compute_next_cron_run_time(cron_expression: str | None, now: datetime | None = None) -> datetime | None:
    """根据五段 cron 表达式计算下一次运行时间。"""
    if not cron_expression:
        return None
    now = now or datetime.utcnow()
    parts = cron_expression.split()
    if len(parts) != 5:
        return None
    try:
        minutes = _parse_cron_field(parts[0], 0, 59)
        hours = _parse_cron_field(parts[1], 0, 23)
        days = _parse_cron_field(parts[2], 1, 31)
        months = _parse_cron_field(parts[3], 1, 12)
        weekdays = _parse_cron_field(parts[4], 0, 7)
    except ValueError:
        return None
    if 7 in weekdays:
        weekdays.add(0)
        weekdays.discard(7)

    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    day_is_wildcard = parts[2] == "*"
    weekday_is_wildcard = parts[4] == "*"
    for _ in range(366 * 24 * 60):
        cron_weekday = (candidate.weekday() + 1) % 7
        day_matches = candidate.day in days
        weekday_matches = cron_weekday in weekdays
        if not day_is_wildcard and not weekday_is_wildcard:
            calendar_matches = day_matches or weekday_matches
        else:
            calendar_matches = day_matches and weekday_matches
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.month in months
            and calendar_matches
        ):
            return candidate
        candidate += timedelta(minutes=1)
    return None


def _parse_cron_field(value: str, minimum: int, maximum: int) -> set[int]:
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            raise ValueError("empty cron field")
        if "/" in item:
            item, step_value = item.split("/", 1)
            step = int(step_value)
            if step <= 0:
                raise ValueError("invalid cron step")
        else:
            step = 1
        if item == "*":
            start, end = minimum, maximum
        elif "-" in item:
            start_value, end_value = item.split("-", 1)
            start, end = int(start_value), int(end_value)
        else:
            start = end = int(item)
        if start < minimum or end > maximum or start > end:
            raise ValueError("cron field out of range")
        result.update(range(start, end + 1, step))
    return result


def sync_task_schedule_state(task: TaskInfo) -> None:
    if task.id is None:
        return
    if task.status != 1:
        clear_task_schedule_state(task.id)
        return
    next_run_time = compute_next_run_time(task)
    if next_run_time is not None:
        task.next_run_time = next_run_time
    TASK_SCHEDULE_CACHE.set_json(str(task.id), value={
        "id": task.id,
        "status": task.status,
        "nextRunTime": task.next_run_time.isoformat() if task.next_run_time else None,
    })


def clear_task_schedule_state(task_id: int) -> None:
    TASK_SCHEDULE_CACHE.delete(str(task_id))
