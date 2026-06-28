"""规则匹配评估器：exact / contains / regex / numeric_tolerance。"""

from __future__ import annotations

import re

from app.modules.workflow_eval.service.evaluator.base import (
    BaseEvaluator,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
)


@EvaluatorRegistry.register("rule_match")
class RuleMatchEvaluator(BaseEvaluator):
    """基于规则的确定性匹配，不依赖外部调用，适合回归基线。"""

    def evaluate(self, ctx: EvalContext) -> EvalResult:
        cfg = ctx.case_config or {}
        mode = cfg.get("mode", "contains")
        # 期望值优先取 case_config.expected_text，其次 ctx.expected（文本/数值均可，各模式自行转换）
        expected_value = cfg.get("expected_text")
        if expected_value is None:
            expected_value = ctx.expected

        actual_str = str(ctx.actual)
        regex_error: str | None = None

        if mode == "exact":
            passed = actual_str == str(expected_value) if expected_value is not None else False
        elif mode == "contains":
            passed = expected_value is not None and str(expected_value) in actual_str
        elif mode == "regex":
            try:
                passed = expected_value is not None and re.search(str(expected_value), actual_str) is not None
            except re.error as exc:
                passed = False
                regex_error = str(exc)
        elif mode == "numeric_tolerance":
            tolerance = float(cfg.get("tolerance", 0))
            try:
                passed = abs(float(ctx.actual) - float(expected_value)) <= tolerance
            except (TypeError, ValueError):
                passed = False
        else:
            passed = False

        score = 1.0 if passed else 0.0
        detail = {"mode": mode, "expected": expected_value, "actual": actual_str[:200]}
        if regex_error is not None:
            detail["regex_error"] = regex_error
        return EvalResult(
            score=score,
            passed=passed,
            detail=detail,
        )
