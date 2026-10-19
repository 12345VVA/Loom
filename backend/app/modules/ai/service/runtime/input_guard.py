"""调用前输入守卫：vision 能力前置校验（AI-013 拆分，纯搬迁）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _check_vision_capability(resolved: dict, messages: list[Any]) -> dict | None:
    """WFI-2c：多模态输入的 vision 前置校验（多模态一期报告 §6.3）。

    消息含 list content（多模态 IR parts）且模型 capabilities 已配置但不含
    vision → 返回 ``{"success": False, "errorMessage": ...}``（沿既有错误流由
    run_ai_chat 转 ValueError）；capabilities 未配置时放行（存量自定义模型不阻断，
    仅 Warning），纯文本调用零影响。
    """
    has_image = False
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, list):
            has_image = True
            break
    if not has_image:
        return None

    model = resolved.get("model")
    capabilities = (getattr(model, "capabilities", None) or "").lower()
    if not capabilities:
        logger.warning("模型 capabilities 未配置，跳过 vision 前置校验（model=%s）", getattr(model, "code", "?"))
        return None
    if "vision" not in [c.strip() for c in capabilities.split(",")]:
        model_code = getattr(model, "code", "未知模型")
        return {
            "success": False,
            "errorMessage": (
                f"当前模型 {model_code} 不支持视觉输入，请切换多模态模型（如 GPT-4o / Qwen-VL）或移除图片绑定"
            ),
        }
    return None
