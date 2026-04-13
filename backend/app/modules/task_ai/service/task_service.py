"""
Task 模块任务服务
"""
from datetime import datetime

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import asc, desc, func
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.data_scope_service import can_access_user, resolve_data_scope
from app.modules.task_ai.model.task import (
    Task,
    TaskCancelRequest,
    TaskCreate,
    TaskRead,
    TaskStatsResponse,
    TaskStatus,
    TaskUpdate,
)
from app.modules.task_ai.tasks.ai_tasks import process_ai_task


class TaskService:
    """任务服务类"""

    def __init__(self, session: Session):
        self.session = session

    def add(
        self,
        payload: TaskCreate,
        background_tasks: BackgroundTasks | None = None,
        current_user: User | None = None,
    ) -> TaskRead:
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

        task = Task(
            user_id=payload.user_id or current_user.id,
            prompt=payload.prompt,
            task_type=payload.task_type,
            status=TaskStatus.PENDING,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        if background_tasks:
            background_tasks.add_task(process_ai_task.delay, str(task.id))

        return task

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[TaskRead]:
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
        
        statement = select(Task)
        statement = self._apply_query(statement, query, current_user)
        return self.session.exec(statement).all()

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[TaskRead]:
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
        
        page = query.page or 1
        page_size = query.size or 10
        
        statement = select(Task)
        statement = self._apply_query(statement, query, current_user)
        
        # 计算总数
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        # 分页执行
        items = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        
        return PageResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def _apply_query(self, statement, query: CrudQuery | None, current_user: User):
        from app.framework.router.query_builder import QueryBuilder
        builder = QueryBuilder(Task, query)
        
        # 处理数据权限
        context = resolve_data_scope(self.session, current_user)
        
        # 链式应用
        statement = builder.apply_data_scope(statement, context, current_user.id)
        statement = builder.apply_filters(statement)
        statement = builder.apply_keyword(statement)
        statement = builder.apply_where(statement)
        statement = builder.apply_sort(statement, fallback_field="created_at")
        
        return statement

    def normalize_payload(self, payload=None, **_kwargs):
        if payload is None or not hasattr(payload, "prompt"):
            return
        payload.prompt = payload.prompt.strip()

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: str | None = None,
        error: str | None = None,
        progress: float | None = None,
    ):
        task = self.session.exec(select(Task).where(Task.id == task_id)).first()

        if task:
            task.status = status
            task.updated_at = datetime.utcnow()

            if result:
                task.result = result
            if error:
                task.error = error
            if progress is not None:
                task.progress = progress

            if status == TaskStatus.PROCESSING and not task.started_at:
                task.started_at = datetime.utcnow()
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.completed_at = datetime.utcnow()

            self.session.commit()
            self.session.refresh(task)

        return task
