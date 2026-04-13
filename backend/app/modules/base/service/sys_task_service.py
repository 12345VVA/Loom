"""
系统任务管理服务
"""
from __future__ import annotations
from typing import Optional
from sqlmodel import select

from app.modules.base.model.sys import SysTask, SysTaskLog
from app.modules.base.service.admin_service import BaseAdminCrudService


class SysTaskService(BaseAdminCrudService):
    """系统任务管理服务"""

    def __init__(self, session):
        super().__init__(session, SysTask)

    def log(self, task_id: int, status: int, detail: Optional[str] = None, consume_time: int = 0):
        """记录任务日志"""
        log = SysTaskLog(
            task_id=task_id,
            status=status,
            detail=detail,
            consume_time=consume_time
        )
        self.session.add(log)
        self.session.commit()
        return log

    def update_run_time(self, task_id: int):
        """更新任务运行时间"""
        from datetime import datetime
        task = self.session.get(SysTask, task_id)
        if task:
            task.prev_run_time = datetime.utcnow()
            # 这里可以根据 cron 计算下一次运行时间
            self.session.add(task)
            self.session.commit()
