"""
Task 模块 AI 异步任务
"""
from app.celery_app import celery_app
from app.modules.task_ai.tasks.ai_task_handlers import handle_text_generation


@celery_app.task(name="app.modules.task_ai.tasks.process_ai_task")
def process_ai_task(task_id: str):
    """处理 AI 生成任务"""
    from app.core.database import get_session
    from app.modules.task_ai.model.task import TaskStatus
    from app.modules.task_ai.service.task_service import TaskService

    session = next(get_session())
    service = TaskService(session)

    try:
        service.update_task_status(task_id, TaskStatus.PROCESSING, progress=0.1)

        task = service.get_task_for_worker(task_id)

        if task.task_type == "text_generation":
            result = handle_text_generation(task.prompt, task_id, service)
            service.update_task_status(
                task_id, TaskStatus.COMPLETED, result=result, progress=1.0
            )
        else:
            service.update_task_status(
                task_id, TaskStatus.FAILED, error="Unknown task type"
            )

        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        service.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
        return {"task_id": task_id, "status": "failed", "error": str(e)}
    finally:
        session.close()
