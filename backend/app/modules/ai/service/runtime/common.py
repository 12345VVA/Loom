"""AI 运行时共享状态：fallback 深度 contextvar 与单次调用上下文（AI-013 拆分）。"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass

from sqlmodel import Session

from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider, AiRuntimeInvocation
from app.modules.ai.service.governance_service import AiGovernanceService

logger = logging.getLogger(__name__)

# 当前请求内 fallback 降级深度：跨 _fallback/_stream_fallback 递归累加，
# 防止 fallback 链成环时 _invoke 失败→_fallback→_invoke 形成无限递归（最终 RecursionError 崩 worker）
_fallback_depth: contextvars.ContextVar[int] = contextvars.ContextVar("ai_fallback_depth", default=0)
MAX_FALLBACK_DEPTH = 5


@dataclass
class _InvocationState:
    """单次模型调用的治理/审计上下文（_invoke 与 _stream_invoke 共用前置流程）。

    `closed` 标记治理收尾（finish/block）是否已发生：流式路径的 finally 兜底
    依赖它避免双重收尾；非流式路径忽略。
    """

    provider: AiProvider
    model: AiModel
    profile: AiModelProfile
    governance: AiGovernanceService
    start: float
    invocation: AiRuntimeInvocation | None = None
    closed: bool = False
    # 生成任务关联（AI-030）：异步调用传入，落调用日志供任务维度成本归集
    task_id: int | None = None

    @classmethod
    def from_resolved(
        cls, session: Session, resolved: dict, start: float, task_id: int | None = None
    ) -> _InvocationState:
        return cls(
            provider=resolved["provider"],
            model=resolved["model"],
            profile=resolved["profile"],
            governance=AiGovernanceService(session),
            invocation=None,
            closed=False,
            start=start,
            task_id=task_id,
        )
