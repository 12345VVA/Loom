"""AI 模块跨层共享常量（单一权威，评审 AI-010）。

新增厂商 / 模型类型时只改本文件 + 对应 adapter 实现，其余清单全部派生：
- factory.ADAPTERS（实现映射）在 import 期与 AI_ADAPTERS 做一致性校验，漂移即启动失败；
- model/ai.py 的 DTO 校验清单、celery_app.py 的队列声明、task_service.py 的
  队列路由均从本文件 import，禁止各自手写字面量副本。

本文件必须保持零依赖（仅标准库），被 model / service / celery_app 多层引用。
"""

from __future__ import annotations

# 支持的厂商适配器键（与 factory.ADAPTERS 的键一一对应，factory import 期强校验）
AI_ADAPTERS: frozenset[str] = frozenset(
    {
        "openai-compatible",
        "ollama",
        "gemini",
        "claude",
        "deepseek",
        "volcengine-ark",
        "bailian",
        "hunyuan",
        "qianfan",
        "zhipu",
        "minimax",
        "mimo",
        "toapis",
        "poryf",
    }
)

# 模型能力类型（决定 DTO 校验、任务类型白名单与队列路由）
AI_MODEL_TYPES: tuple[str, ...] = ("chat", "embedding", "image", "audio", "video", "rerank")

# Celery 队列名（顺序与 worker -Q 参数、compose 配置保持一致）
AI_TASK_QUEUES: tuple[str, ...] = ("ai.chat", "ai.image", "ai.embedding", "ai.rerank", "ai.audio", "ai.video")

if set(AI_TASK_QUEUES) != {f"ai.{t}" for t in AI_MODEL_TYPES}:
    raise RuntimeError(
        f"AI_TASK_QUEUES 与 AI_MODEL_TYPES 派生不一致: {set(AI_TASK_QUEUES) ^ {f'ai.{t}' for t in AI_MODEL_TYPES}}"
    )


def ai_task_queue(model_type: str) -> str:
    """按模型类型返回 Celery 队列名（task_service 投递与 celery_app 声明共用）。"""
    if model_type not in AI_MODEL_TYPES:
        raise ValueError(f"不支持的 AI 模型类型: {model_type}")
    return f"ai.{model_type}"
