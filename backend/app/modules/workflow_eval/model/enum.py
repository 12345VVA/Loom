"""评价系统枚举常量。"""

from __future__ import annotations


class EvalRunStatus:
    """评估运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"  # 部分用例 error/timeout 但运行完成
    CANCELLED = "cancelled"

    ALL = (PENDING, RUNNING, SUCCEEDED, FAILED, PARTIAL, CANCELLED)
    TERMINAL = (SUCCEEDED, FAILED, PARTIAL, CANCELLED)


class CaseResultStatus:
    """单条用例结果状态。"""

    SUCCESS = "success"  # 执行成功且通过
    FAIL = "fail"  # 执行成功但未通过评估
    ERROR = "error"  # 执行异常
    TIMEOUT = "timeout"  # 执行超时
    BLOCKED = "blocked"  # 被配额/治理拦截，不计入 fail


class EvaluatorType:
    """评估器类型。"""

    RULE_MATCH = "rule_match"
    LLM_JUDGE = "llm_judge"
    COMPOSITE = "composite"

    ALL = (RULE_MATCH, LLM_JUDGE, COMPOSITE)
