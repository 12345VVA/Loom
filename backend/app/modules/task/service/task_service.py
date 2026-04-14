"""
系统定时任务服务
"""
from __future__ import annotations

from datetime import datetime
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


class TaskInfoService(BaseAdminCrudService):
    """系统定时任务服务"""

    def __init__(self, session: Session):
        super().__init__(session, TaskInfo)

    def _after_add(self, data: dict, entity: Any) -> Any:
        # TODO: 注册调度任务到引擎
        pass
        return entity

    def _after_update(self, data: dict, entity: Any) -> Any:
        # TODO: 重置调度任务
        pass
        return entity

    def _before_delete(self, ids: list[int]) -> None:
        for row in list(self.session.exec(select(TaskInfo).where(TaskInfo.id.in_(ids))).all()):
            # TODO: 从引擎移除调度
            pass

    def log(self, query: CrudQuery) -> PageResult[TaskLogRead]:
        """查询任务日志"""
        page = query.page or 1
        page_size = query.size or 10
        id_val = query.params.get("id")
        status_val = query.params.get("status")

        statement = select(TaskLog, TaskInfo.name.label("taskName")).join(
            TaskInfo, TaskLog.taskId == TaskInfo.id
        )
        if id_val:
            statement = statement.where(TaskLog.taskId == id_val)
        if status_val is not None:
            statement = statement.where(TaskLog.status == status_val)
        
        statement = statement.order_by(TaskLog.created_at.desc())
        
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        results = self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()
        
        items = []
        for log_row, task_name in results:
            items.append(TaskLogRead(
                id=log_row.id,
                taskId=log_row.taskId,
                taskName=task_name,
                status=log_row.status,
                detail=log_row.detail,
                consumeTime=log_row.consumeTime,
                createTime=log_row.created_at
            ))

        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def start(self, id: int):
        """启动任务"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        row.status = 1
        self.session.add(row)
        self.session.commit()
        # TODO: 调用调度引擎启动
        return {"success": True}

    async def stop(self, id: int):
        """停止任务"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        row.status = 0
        self.session.add(row)
        self.session.commit()
        # TODO: 调用调度引擎停止
        return {"success": True}

    async def once(self, id: int):
        """立即执行一次"""
        row = self.session.get(TaskInfo, id)
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 异步触发 Celery 任务
        from app.modules.task.tasks.system_tasks import execute_system_task
        print(f"Dispatching task {id} to Celery...")
        execute_system_task.delay(id)
        
        return {"success": True}

