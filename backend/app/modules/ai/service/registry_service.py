"""AI 模型调用配置解析服务。"""

from __future__ import annotations

from typing import TypeVar

from sqlmodel import Session, select

from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.ai.service.errors import AiInvocationError
from app.modules.ai.service.utils import _loads, normalize_response_format

_EntityT = TypeVar("_EntityT")


def live_record(obj: _EntityT | None) -> _EntityT | None:
    """软删除不变量（AI-001）：delete_time 非空即已删除，运行时解析一律视同不存在。

    session.get() 与手写 select 都不会自动过滤软删行，所有运行时解析路径
    （resolve / _fallback / _stream_fallback）必须经由本 helper 判定，防止
    后台"删除"的配置仍被调用并计费。
    """
    if obj is None or getattr(obj, "delete_time", None) is not None:
        return None
    return obj


class AiModelRegistryService:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, *, model_type: str, scenario: str = "default", profile_code: str | None = None) -> dict:
        if profile_code:
            profile = self.session.exec(
                select(AiModelProfile).where(
                    AiModelProfile.code == profile_code,
                    AiModelProfile.is_active == True,  # noqa: E712
                    AiModelProfile.delete_time == None,  # noqa: E711
                )
            ).first()
        else:
            profile = self.session.exec(
                select(AiModelProfile)
                .join(AiModel, AiModel.id == AiModelProfile.model_id)
                .where(
                    AiModelProfile.scenario == scenario,
                    AiModelProfile.is_default == True,  # noqa: E712
                    AiModelProfile.is_active == True,  # noqa: E712
                    AiModelProfile.delete_time == None,  # noqa: E711
                    AiModel.model_type == model_type,
                    AiModel.is_active == True,  # noqa: E712
                    AiModel.delete_time == None,  # noqa: E711
                )
                .order_by(AiModelProfile.sort_order.desc(), AiModelProfile.created_at.desc())
            ).first()
        if not profile:
            raise AiInvocationError("未找到可用的模型调用配置", status_code=404)
        model = live_record(self.session.get(AiModel, profile.model_id))
        if not model or not model.is_active:
            raise AiInvocationError("模型不存在或已禁用", status_code=400)
        provider = live_record(self.session.get(AiProvider, model.provider_id))
        if not provider or not provider.is_active:
            raise AiInvocationError("模型厂商不存在或已禁用", status_code=400)
        if model.model_type != model_type:
            raise AiInvocationError("调用配置模型类型不匹配", status_code=400)
        return {
            "profile": profile,
            "model": model,
            "provider": provider,
            "options": self._merge_options(model, profile),
        }

    def resolve_context_window(self, profile_code: str) -> int | None:
        """渠道能力元数据（E15，公共查询接口）：解析链（profile + fallback 链）所有候选
        模型的 context_window 齐备可信时返回**最小值**；任一候选缺失/不可信（软删、禁用、
        未知窗口）返回 None——调用方不得假设 ≥32k 下界（未知窗口不放行）。

        供 agent 发布校验与 run 发起重校验消费；ai 其他调用方不感知。
        """
        profile = self.session.exec(
            select(AiModelProfile).where(
                AiModelProfile.code == profile_code,
                AiModelProfile.is_active == True,  # noqa: E712
                AiModelProfile.delete_time == None,  # noqa: E711
            )
        ).first()
        if profile is None:
            return None
        from app.modules.ai.service.runtime.common import MAX_FALLBACK_DEPTH

        windows: list[int] = []
        cursor: AiModelProfile | None = profile
        visited: set[int] = set()
        while cursor is not None and cursor.id not in visited and len(visited) <= MAX_FALLBACK_DEPTH:
            visited.add(cursor.id)
            model = live_record(self.session.get(AiModel, cursor.model_id))
            if model is None or not model.is_active or model.context_window is None:
                return None  # 任一候选未知 → 整链不可信（E15 规则 2）
            windows.append(int(model.context_window))
            if not cursor.fallback_profile_id:
                break
            cursor = live_record(self.session.get(AiModelProfile, cursor.fallback_profile_id))
            if cursor is not None and not cursor.is_active:
                return None
        return min(windows) if windows else None

    def _merge_options(self, model: AiModel, profile: AiModelProfile) -> dict:
        options = _loads(model.default_config)
        if profile.custom_config:
            custom = _loads(profile.custom_config)
            if isinstance(custom, dict):
                options.update(custom)
        if profile.temperature is not None:
            options["temperature"] = profile.temperature
        if profile.top_p is not None:
            options["top_p"] = profile.top_p
        if profile.max_tokens is not None:
            options["max_tokens"] = profile.max_tokens
        if profile.timeout is not None:
            options["timeout"] = profile.timeout
        if profile.response_format:
            response_format = normalize_response_format(_loads(profile.response_format))
            if response_format:
                options["response_format"] = response_format
        if profile.tools_config:
            tools = _loads(profile.tools_config)
            if tools:
                options["tools"] = tools
        return options
