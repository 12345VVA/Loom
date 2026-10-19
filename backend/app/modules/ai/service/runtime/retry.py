"""上游调用重试：分类判定 + 指数退避（AI-013 拆分，AI-025 分类语义）。"""

from __future__ import annotations

import time as time_module
from typing import Any

from app.modules.ai.model.ai import AiModelProfile
from app.modules.ai.service.adapters.base import AdapterInputError, UnsupportedCapabilityError
from app.modules.ai.service.utils import _adapter_timeout, _options_without_governance

# 重试退避上限（AI-025）：指数退避封顶，避免 retry_delay 较大时第 N 次重试前阻塞线程过久
_RETRY_DELAY_CAP_SECONDS = 30

# 代码缺陷类异常：重试多少次结果都一样，只会让同一个 bug 在日志里放大 N 倍。
# 刻意用「黑名单」而非「瞬态白名单」——上游可能用无状态码的自定义异常表达真实
# 瞬态故障（如 media_fetch 的参考图下载失败），白名单会把这些退化为不重试
_DEFECT_EXCEPTION_TYPES = (
    TypeError,
    AttributeError,
    KeyError,
    IndexError,
    NameError,
    AssertionError,
    NotImplementedError,
)


def _is_retryable(exc: Exception) -> bool:
    """按异常携带的 HTTP 语义判定是否值得重试（AI-025）。

    - 408/429/5xx：上游过载或临时故障，可重试；
    - 其余 4xx（401/403/400/内容审核拒绝）：重试结果相同，不重试；
    - 无 status_code：默认视为网络层/自定义上游故障，可重试，但排除代码缺陷类
      异常（P2：此前 TypeError 等也会被重试，白烧时间并污染日志）。
    兼容两类载体：UpstreamApiError（http 适配器统一转换）与 OpenAI SDK 异常
    （APIStatusError 等自带 status_code 属性）。
    """
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        return not isinstance(exc, _DEFECT_EXCEPTION_TYPES)
    return status_code >= 500 or status_code in (408, 429)


class RetryMixin:
    def _invoke_with_retry(
        self, adapter, method: str, profile: AiModelProfile, model_code: str, kwargs: dict[str, Any]
    ) -> dict:
        attempts = max(0, int(profile.retry_count or 0)) + 1
        retry_delay = max(0, int(profile.retry_delay_seconds or 0))
        raw_options = dict(kwargs.get("options") or {})
        # timeout 要从未过滤的 options 里取：_options_without_governance 会摘掉它
        effective_timeout = raw_options.get("timeout") or profile.timeout
        # 过滤与重试无关，循环外算一次：既省重复计算，也避免同一个保留键告警每轮刷一遍
        filtered_options = _options_without_governance(raw_options)
        last_exc: Exception | None = None
        for index in range(attempts):
            try:
                call_kwargs = dict(kwargs)
                # 每轮给一份新副本：适配器会原地 pop options（如百炼 image_protocol），
                # 共用同一 dict 会让重试看到被吃过的参数
                call_kwargs["options"] = dict(filtered_options)
                # 超时上下文产出的是本次调用专用副本（池化 adapter 不在原地改）
                with _adapter_timeout(adapter, effective_timeout) as call_adapter:
                    return getattr(call_adapter, method)(model=model_code, **call_kwargs)
            except UnsupportedCapabilityError:
                raise
            except AdapterInputError:
                # 参数/配置错误重试结果相同，直接透出（AI-009）
                raise
            except Exception as exc:
                last_exc = exc
                if index >= attempts - 1:
                    break
                # AI-025：只对瞬态错误重试（网络失败/408/429/5xx）；401/403/400/审核拒绝
                # 重试结果相同，白烧时间还放大上游计费。指数退避封顶 30s，替代固定 sleep
                if not _is_retryable(exc):
                    raise
                if retry_delay:
                    time_module.sleep(min(retry_delay * (2**index), _RETRY_DELAY_CAP_SECONDS))
        raise last_exc or RuntimeError("模型调用失败")
