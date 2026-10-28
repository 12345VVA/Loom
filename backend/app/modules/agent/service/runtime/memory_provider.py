"""会话历史记忆注入 provider（批 C3：enable_memory 的执行期消费者）。

v1 记忆源 = 本会话近期对话（AgentMessage 按 session_id 倒序取 N 条）——agent 自有
数据，无跨模块作用域问题；workflow 语义记忆（search_memories 需 definition_id +
memory_env 分域）与 chat 型 agent 作用域不匹配，留待 agent 记忆专项立项。

注入通道（零改图）：MemoryInjectionMiddleware delta["injected_context"] →
build_model_messages 剩余预算 20% 的注入段 → "[参考上下文]" 第二条 SystemMessage。
下游截断与预算归裁剪器管，provider 只做粗截防止一次吃满 allotment
（E15 动态预算下限 1000 时注入段 ≈200 token）。

排除语义：最新一条 user 行不注入——首轮它就是当前输入（裁剪器优先级②已完整保留，
注入即重复）；恢复轮（E4）无新 user 输入，排除的是发起时诉求，可接受（恢复上下文
主要靠组结果 ToolMessage 重建）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func
from sqlmodel import select

from app.modules.agent.model.agent import AgentMessage
from app.modules.agent.service.runtime.middleware import RunContext

logger = logging.getLogger("agent.memory")

_HISTORY_LIMIT = 10  # 最近 N 条（user/assistant 近似交替）
_MAX_CHARS = 2000  # 粗截上限（下游裁剪器还有 allotment 截断）


def make_session_history_provider(db: Any) -> Any:
    """会话历史 provider 工厂：闭包捕获 worker 线程自建 Session（graph.invoke 与装配
    同线程，Session 全程有效——不跨线程、不交给自管事务的外部函数）。

    degrade 兜底：apply_pre_model_hooks 不捕异常，检索故障若外抛会把整轮 run 打成
    failed——provider 内部吞异常返回空串（对齐 workflow recall 节点降级哲学）。
    """

    def provider(ctx: RunContext | None) -> str:
        if ctx is None or not ctx.session_id:
            return ""
        try:
            latest_user = (
                select(func.max(AgentMessage.id))
                .where(
                    AgentMessage.session_id == ctx.session_id,
                    AgentMessage.role == "user",
                    AgentMessage.delete_time == None,  # noqa: E711
                )
                .scalar_subquery()
            )
            rows = db.exec(
                select(AgentMessage)
                .where(
                    AgentMessage.session_id == ctx.session_id,
                    AgentMessage.role.in_(["user", "assistant"]),  # type: ignore[attr-defined]
                    AgentMessage.delete_time == None,  # noqa: E711
                    AgentMessage.id != latest_user,
                )
                .order_by(AgentMessage.id.desc())  # type: ignore[attr-defined]
                .limit(_HISTORY_LIMIT)
            ).all()
            lines = [
                f"{'用户' if r.role == 'user' else '助手'}：{(r.content or '').strip()}"
                for r in reversed(rows)
                if (r.content or "").strip()
            ]
            text = "\n".join(lines)
            if len(text) > _MAX_CHARS:
                text = text[:_MAX_CHARS] + "…"
            return text
        except Exception:  # noqa: BLE001 —— 记忆注入失败降级为空，不拖垮 run
            logger.warning("agent 会话历史注入失败 session=%s（降级为空）", ctx.session_id, exc_info=True)
            return ""

    return provider
