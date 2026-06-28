"""LLM-as-judge 评估器：复用 AI 运行时对输出打分。

通过注入 judge_fn 解耦真实 LLM 调用：case_config.judge_fn = Callable[[input, actual, expected], float]，
返回 [0,1] 分。批量执行时由 eval_tasks 用 build_default_judge_fn 构造（复用 workflow.run_ai_chat）；
测试时可注入 mock。未注入时返回中性分（0.5，不通过），交由其他评估器主导。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from app.modules.workflow_eval.service.evaluator.base import (
    BaseEvaluator,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
)

logger = logging.getLogger(__name__)

# 评分官系统提示：要求严格 JSON 输出，便于鲁棒解析
DEFAULT_JUDGE_SYSTEM_PROMPT = (
    "你是严格的质量评分官。请根据【期望输出】对【实际输出】打分，"
    "输出 0.0（完全不符）到 1.0（完全符合）之间的分数。"
    '只返回 JSON：{"score": <0-1 的浮点数>, "reason": "<不超过 50 字的简短理由>"}，不要包含任何其他文本。'
)

# 默认 user prompt 模板，支持 {input}/{actual}/{expected} 占位（可用 case_config.judge_prompt 覆盖）
DEFAULT_JUDGE_USER_TEMPLATE = (
    "【输入】\n{input}\n\n【期望输出】\n{expected}\n\n【实际输出】\n{actual}\n\n请严格按格式评分。"
)

# 单字段最大长度，避免 prompt 过长
_MAX_FIELD_CHARS = 2000


def _truncate(value: Any) -> str:
    """任意值转字符串并截断，防止单条 case 输出撑爆 judge prompt。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= _MAX_FIELD_CHARS else text[:_MAX_FIELD_CHARS] + "…(截断)"


def _parse_score(content: str) -> float:
    """从 LLM 回复中解析 [0,1] 分数：JSON.score 优先 → 首个 0~1 浮点 → 回退 0.5。"""
    text = (content or "").strip()
    # 1. JSON {"score": x} 或裸数字
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "score" in data:
            return float(data["score"])
        if isinstance(data, (int, float)):
            return float(data)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # 2. 正则兜底：首个 0~1 浮点（兼容 "分数：0.8" / "0.85" 等）
    match = re.search(r"([01](?:\.\d+)?|0?\.\d+)", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 0.5


def build_default_judge_fn(
    profile_code: str, prompt_template: str | None = None
) -> Callable[[Any, Any, Any], float]:
    """构造复用 workflow.run_ai_chat 的默认 judge_fn。

    profile_code：AI 模型 Profile 编码（用例 evaluator_config.judge_profile_code 或全局兜底）。
    prompt_template：可选自定义 user prompt（含 {input}/{actual}/{expected} 占位），缺省用内置模板。
    返回的 judge_fn 在 LLMJudgeEvaluator.evaluate 中调用；调用异常会被评估器 try/except 兜底为 0 分。
    """
    template = prompt_template or DEFAULT_JUDGE_USER_TEMPLATE

    def judge_fn(input_data: Any, actual: Any, expected: Any) -> float:
        # 延迟 import，避免模块加载循环
        from app.modules.workflow.service.workflow_service import run_ai_chat

        user_prompt = template.format(
            input=_truncate(input_data),
            actual=_truncate(actual),
            expected=_truncate(expected),
        )
        content = run_ai_chat(
            profile_code,
            user_prompt,
            system_prompt=DEFAULT_JUDGE_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
        )
        return max(0.0, min(1.0, _parse_score(content)))

    return judge_fn


@EvaluatorRegistry.register("llm_judge")
class LLMJudgeEvaluator(BaseEvaluator):
    def evaluate(self, ctx: EvalContext) -> EvalResult:
        cfg = ctx.case_config or {}
        judge_fn: Callable[[Any, Any, Any], float] | None = cfg.get("judge_fn")

        if judge_fn is None:
            return EvalResult(
                score=0.5,
                passed=False,
                detail={"note": "llm_judge 未注入 judge_fn，跳过实际评分"},
            )

        try:
            raw_score = float(judge_fn(ctx.input_data, ctx.actual, ctx.expected))
        except Exception as exc:  # judge 异常不应拖垮整批评估
            return EvalResult(score=0.0, passed=False, detail={"error": str(exc)})

        score = max(0.0, min(1.0, raw_score))
        threshold = float(cfg.get("threshold", 0.6))
        return EvalResult(
            score=score,
            passed=score >= threshold,
            detail={"score": score, "threshold": threshold},
        )
