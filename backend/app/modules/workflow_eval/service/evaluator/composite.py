"""组合评估器：按 weight 加权多个子评估器，任一不过则整体不过。"""

from __future__ import annotations

from app.modules.workflow_eval.service.evaluator.base import (
    BaseEvaluator,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
)


@EvaluatorRegistry.register("composite")
class CompositeEvaluator(BaseEvaluator):
    """case_config.children = [{type, config, weight}, ...]。

    加权平均 score；passed 取所有子评估器全部通过（AND 语义）。
    """

    def evaluate(self, ctx: EvalContext) -> EvalResult:
        cfg = ctx.case_config or {}
        children = cfg.get("children", [])

        total_weight = 0.0
        weighted_score = 0.0
        all_passed = True
        details: dict = {}

        for child in children:
            child_type = child.get("type", "rule_match")
            child_cfg = child.get("config", {})
            weight = float(child.get("weight", 1.0))

            sub_evaluator = EvaluatorRegistry.get(child_type)
            sub_result = sub_evaluator.evaluate(
                EvalContext(
                    input_data=ctx.input_data,
                    expected=ctx.expected,
                    actual=ctx.actual,
                    case_config=child_cfg,
                )
            )

            weighted_score += sub_result.score * weight
            total_weight += weight
            if not sub_result.passed:
                all_passed = False
            details[child_type] = sub_result.detail

        score = weighted_score / total_weight if total_weight else 0.0
        # 空 children：无任何校验规则，不应判为通过（避免「0 分却 passed=true」的矛盾结果污染 pass_rate/回归对比）
        if not children:
            all_passed = False
            details["error"] = "composite 评估器未配置 children"
        return EvalResult(score=score, passed=all_passed, detail=details)
