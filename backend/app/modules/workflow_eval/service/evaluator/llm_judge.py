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

# 默认评分维度（case_config.rubric 可覆盖）。基础版：正确性 / 完整性 / 清晰度
DEFAULT_RUBRIC_DIMENSIONS = ("correctness", "completeness", "clarity")

# 评分官系统提示：按维度各自打分 + 总分 + 简短理由（{rubric} 由 build_default_judge_fn 填充）。
# JSON 示例的花括号需转义为 {{ }}，避免 .format() 误当作占位符。
DEFAULT_JUDGE_SYSTEM_PROMPT = (
    "你是严格的质量评分官。请按以下维度各自打 0.0（极差）到 1.0（极好）的分，"
    "并给出总分与简短理由：{rubric}。"
    '只返回 JSON：{{"score": <0-1 总分>, "dimensions": {{"<维度>": <0-1>}}, "reason": "<不超过 80 字的简短理由>"}}，'
    "不要包含任何其他文本。"
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


def _parse_judge_result(content: str, rubric: tuple[str, ...] | None = None) -> dict:
    """解析 judge 输出为 {score, dimensions, reason}。

    优先解析 {"score", "dimensions", "reason"} JSON；无总分时取维度均值；失败 fallback 到
    _parse_score（兼容只返回分数/非 JSON），dimensions/reason 留空。reason 截断 500 字。
    """
    text = (content or "").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            score: float = 0.5
            if "score" in data:
                score = float(data["score"])
            elif isinstance(data.get("dimensions"), dict) and data["dimensions"]:
                vals = [float(v) for v in data["dimensions"].values() if isinstance(v, (int, float))]
                score = sum(vals) / len(vals) if vals else 0.5
            dims: dict[str, float] = {}
            if isinstance(data.get("dimensions"), dict):
                for k, v in data["dimensions"].items():
                    try:
                        dims[str(k)] = max(0.0, min(1.0, float(v)))
                    except (TypeError, ValueError):
                        continue
            reason = str(data["reason"])[:500] if data.get("reason") else ""
            return {"score": max(0.0, min(1.0, score)), "dimensions": dims, "reason": reason}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {"score": _parse_score(text), "dimensions": {}, "reason": ""}


def build_default_judge_fn(
    profile_code: str,
    prompt_template: str | None = None,
    rubric: tuple[str, ...] | list[str] | None = None,
    samples: int = 1,
) -> Callable[[Any, Any, Any], dict]:
    """构造复用 workflow.run_ai_chat 的默认 judge_fn（返回多维 rubric 结果）。

    profile_code：AI 模型 Profile 编码（用例 evaluator_config.judge_profile_code 或全局兜底）。
    prompt_template：可选自定义 user prompt（含 {input}/{actual}/{expected} 占位），缺省用内置模板。
    rubric：评分维度（case_config.rubric），缺省用 DEFAULT_RUBRIC_DIMENSIONS。
    samples：self-consistency 采样次数（case_config.samples，默认 1）。>1 时多次采样取均值降方差
        （需 profile temperature>0 才有效；返回 detail 加 std/samples）。token 成本随 samples 线性增长。
    返回的 judge_fn 返回 {score, dimensions, reason[, std, samples]}；调用异常会被评估器兜底为 0 分。
    """
    dims = tuple(rubric) if rubric else DEFAULT_RUBRIC_DIMENSIONS
    template = prompt_template or DEFAULT_JUDGE_USER_TEMPLATE
    system_prompt = DEFAULT_JUDGE_SYSTEM_PROMPT.format(rubric="、".join(dims))
    n = max(1, int(samples))

    def judge_fn(input_data: Any, actual: Any, expected: Any) -> dict:
        # 延迟 import，避免模块加载循环
        from app.modules.workflow.service.workflow_service import run_ai_chat

        user_prompt = template.format(
            input=_truncate(input_data),
            actual=_truncate(actual),
            expected=_truncate(expected),
        )

        if n == 1:
            content = run_ai_chat(
                profile_code, user_prompt, system_prompt=system_prompt,
                response_format={"type": "json_object"},
            )
            return _parse_judge_result(content, dims)

        # self-consistency（P1-3）：n 次采样取均值降方差
        results: list[dict] = []
        for _ in range(n):
            content = run_ai_chat(
                profile_code, user_prompt, system_prompt=system_prompt,
                response_format={"type": "json_object"},
            )
            results.append(_parse_judge_result(content, dims))
        scores = [r["score"] for r in results]
        agg_score = sum(scores) / n
        dim_acc: dict[str, list[float]] = {}
        for r in results:
            for k, v in r["dimensions"].items():
                dim_acc.setdefault(k, []).append(v)
        agg_dims = {k: round(sum(v) / len(v), 4) for k, v in dim_acc.items()}
        std = (sum((s - agg_score) ** 2 for s in scores) / n) ** 0.5
        return {
            "score": round(agg_score, 4),
            "dimensions": agg_dims,
            "reason": results[0]["reason"],
            "std": round(std, 4),
            "samples": n,
        }

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
            raw = judge_fn(ctx.input_data, ctx.actual, ctx.expected)
        except Exception as exc:  # judge 异常不应拖垮整批评估
            return EvalResult(score=0.0, passed=False, detail={"error": str(exc)})

        # 兼容 dict（多维 rubric：{score, dimensions, reason}）与 float（旧实现/测试 mock）
        if isinstance(raw, dict):
            score = max(0.0, min(1.0, float(raw.get("score", 0.5))))
            dimensions = raw.get("dimensions") or {}
            reason = raw.get("reason") or ""
        else:
            score = max(0.0, min(1.0, float(raw)))
            dimensions = {}
            reason = ""

        threshold = float(cfg.get("threshold", 0.6))
        return EvalResult(
            score=score,
            passed=score >= threshold,
            detail={
                "score": score,
                "threshold": threshold,
                "dimensions": dimensions,
                "reason": reason,
            },
        )
