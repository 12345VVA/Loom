"""agent 链路耗时打点：统一计时上下文管理器。

设计（错误处理收尾专项批次 1，排查「agent 响应每次都慢」）：
- 级别策略：每 run 恒定 4 条 INFO（req.total / worker.graph_invoke / worker.finish_commit /
  llm.round×N）+ 细粒度段 DEBUG + 慢调用升级 WARN + 段内异常 ERROR；
- 与 ai 侧 extra 风格一致（latency_ms/phase...），JsonFormatter/ConsoleFormatter
  对任意 extra 自动透传（core/logging.py 遍历 record.__dict__），文件侧可按字段检索；
- 逐轮 LLM 的渠道纯耗时以 ai_model_call_log.latency_ms 审计行为准（task_id=trace.id
  可 join），本模块的 llm.round 边界差值 = ai 侧本地开销（治理/PII 脱敏/审计 commit），
  两者结合可分解「渠道慢 vs 本地慢」。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings

# agent 模块既有 logger 均为 agent.* 前缀（agent.run_service / agent.graph ...），
# app.* 前缀是 framework 异常通道（app.exceptions）的约定
logger = logging.getLogger("agent.timing")

_SLOW_THRESHOLD_BY_KIND = {
    "model": "AGENT_TIMING_SLOW_MODEL_MS",
    "tool": "AGENT_TIMING_SLOW_TOOL_MS",
    "phase": "AGENT_TIMING_SLOW_PHASE_MS",
}


def _slow_threshold_ms(kind: str) -> int:
    value = getattr(settings, _SLOW_THRESHOLD_BY_KIND[kind], 0)
    return int(value or 0)


@contextmanager
def timed(
    phase: str,
    *,
    level: int = logging.DEBUG,
    slow: str | None = None,
    message: str = "",
    **fields: Any,
) -> Generator[dict[str, Any], None, None]:
    """计时上下文：正常退出按 level 记录（达 slow 阈值升级 WARN），异常退出记 ERROR 后原样抛出。

    with timed("llm.round", level=logging.INFO, slow="model", trace_token=tok) as bag:
        bag["round"] = 3  # 运行中才可知的字段中途补

    用法注意：耗时数值在本函数内部，外部如需（如 model_finished.latencyMs）自行
    perf_counter 起止——CM 的 duration 不外露是有意的（避免两套口径）。
    """
    started = time.perf_counter()
    bag: dict[str, Any] = dict(fields)
    try:
        yield bag
    except BaseException as exc:
        bag.setdefault("error_type", type(exc).__name__)
        bag["status"] = "error"
        logger.error(
            message or f"{phase} 异常终止",
            extra={"phase": phase, "duration_ms": int((time.perf_counter() - started) * 1000), **bag},
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    log_level = level
    if slow is not None and _slow_threshold_ms(slow) and duration_ms >= _slow_threshold_ms(slow):
        log_level = logging.WARNING
    bag.setdefault("status", "ok")
    logger.log(
        log_level,
        message or f"{phase} 耗时",
        extra={"phase": phase, "duration_ms": duration_ms, **bag},
    )
