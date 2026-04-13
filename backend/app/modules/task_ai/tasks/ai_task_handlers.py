"""
Task 模块 AI 任务处理器
"""
from openai import OpenAI

from app.core.config import settings
from app.modules.task_ai.model.task import TaskStatus


def handle_text_generation(prompt: str, task_id: str, service) -> str:
    """处理文本生成任务"""
    try:
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        service.update_task_status(task_id, TaskStatus.PROCESSING, progress=0.3)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
        )

        result = response.choices[0].message.content
        return result or ""

    except Exception as e:
        raise Exception(f"Text generation failed: {str(e)}")
