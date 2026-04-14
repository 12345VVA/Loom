"""
系统任务分发逻辑 (Celery Tasks)
"""
import time
from datetime import datetime
from app.celery_app import celery_app
from app.core.database import Session, engine
from app.modules.task.model.task import TaskInfo, TaskLog
from app.modules.task.service.task_invoker import TaskInvoker

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

        log = TaskLog(taskId=task_id, status=1)
        try:
            # 更新最后执行时间
            task.lastExecuteTime = datetime.utcnow()
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
            log.consumeTime = int((time.time() - start_time) * 1000)
            session.add(log)
            session.commit()
            return f"Task executed with status: {log.status}"
