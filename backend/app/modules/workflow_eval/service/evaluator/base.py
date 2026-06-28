"""评估器抽象与注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EvalContext:
    """评估上下文。"""

    input_data: Any  # 工作流输入
    expected: Any  # 期望输出（用例配置）
    actual: Any  # 实际输出
    case_config: dict = field(default_factory=dict)  # 用例专属评估器配置


@dataclass
class EvalResult:
    """评估结果。"""

    score: float  # [0,1]
    passed: bool
    detail: dict = field(default_factory=dict)


class BaseEvaluator(ABC):
    """评估器基类。evaluate 为同步签名；含 LLM 调用的评估器由调用方（T9c）用 to_thread 卸载。"""

    type: str = ""

    @abstractmethod
    def evaluate(self, ctx: EvalContext) -> EvalResult:
        """对 ctx.actual 相对 ctx.expected 打分，返回 [0,1] 分与是否通过。"""


class EvaluatorRegistry:
    """评估器注册表（参考 NodeExecutorRegistry）。"""

    _registry: dict[str, type[BaseEvaluator]] = {}

    @classmethod
    def register(cls, type_: str) -> Callable[[type], type]:
        def decorator(klass: type) -> type:
            cls._registry[type_] = klass
            klass.type = type_
            return klass

        return decorator

    @classmethod
    def get(cls, type_: str) -> BaseEvaluator:
        klass = cls._registry.get(type_)
        if klass is None:
            raise ValueError(f"未知评估器类型: {type_}，已注册: {cls.available()}")
        return klass()

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._registry.keys())
