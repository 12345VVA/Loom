"""JSON 结构校验评估器：keys（含指定字段）/ exact_keys（字段集合完全相等）。

补充 rule_match（文本匹配）与 llm_judge（LLM 打分）之间的确定性结构校验——
工作流常产出结构化 JSON（如 {title, summary, tags}），用本评估器校验字段齐全，
不必为"字段是否存在"这种确定性问题消耗 LLM 调用。
"""

from __future__ import annotations

import json

from app.modules.workflow_eval.service.evaluator.base import (
    BaseEvaluator,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
)


@EvaluatorRegistry.register("json_schema")
class JsonSchemaEvaluator(BaseEvaluator):
    """校验 actual（JSON 对象）的字段结构符合配置。

    case_config:
      mode: "keys"（默认，含全部 expected_keys 即过，部分命中按比例计分）| "exact_keys"（字段集合完全相等）
      expected_keys: list[str]；缺省取 ctx.expected（list/tuple/set）
    """

    def evaluate(self, ctx: EvalContext) -> EvalResult:
        cfg = ctx.case_config or {}
        mode = cfg.get("mode", "keys")
        expected_keys = set(
            cfg.get("expected_keys")
            or (ctx.expected if isinstance(ctx.expected, (list, tuple, set)) else [])
        )

        try:
            actual = json.loads(ctx.actual) if isinstance(ctx.actual, str) else ctx.actual
        except (json.JSONDecodeError, TypeError):
            return EvalResult(score=0.0, passed=False, detail={"error": "actual 不是合法 JSON"})
        if not isinstance(actual, dict):
            return EvalResult(score=0.0, passed=False, detail={"error": "actual 不是 JSON 对象"})

        actual_keys = set(actual.keys())
        if mode == "exact_keys":
            passed = actual_keys == expected_keys
            return EvalResult(
                score=1.0 if passed else 0.0,
                passed=passed,
                detail={
                    "mode": mode,
                    "actual_keys": sorted(actual_keys),
                    "expected_keys": sorted(expected_keys),
                },
            )

        # mode == "keys"：含全部 expected_keys 即过，部分按比例计分
        if not expected_keys:
            return EvalResult(
                score=1.0,
                passed=True,
                detail={"mode": mode, "note": "未配置 expected_keys，跳过校验"},
            )
        hit = len(actual_keys & expected_keys)
        score = round(hit / len(expected_keys), 4)
        passed = hit == len(expected_keys)
        return EvalResult(
            score=score,
            passed=passed,
            detail={
                "mode": mode,
                "hit": hit,
                "total": len(expected_keys),
                "missing": sorted(expected_keys - actual_keys),
                "extra": sorted(actual_keys - expected_keys),
            },
        )
