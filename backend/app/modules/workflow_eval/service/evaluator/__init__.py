"""评估器注册表与内置实现。

参考 NodeExecutorRegistry 模式：@EvaluatorRegistry.register("type") 装饰器注册，
EvaluatorRegistry.get(type) 取实例。import 本包即触发所有内置评估器注册。
"""

from app.modules.workflow_eval.service.evaluator.base import (
    BaseEvaluator,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
)
from app.modules.workflow_eval.service.evaluator.composite import CompositeEvaluator
from app.modules.workflow_eval.service.evaluator.llm_judge import LLMJudgeEvaluator
from app.modules.workflow_eval.service.evaluator.rule_match import RuleMatchEvaluator

__all__ = [
    "BaseEvaluator",
    "EvalContext",
    "EvalResult",
    "EvaluatorRegistry",
    "RuleMatchEvaluator",
    "CompositeEvaluator",
    "LLMJudgeEvaluator",
]
