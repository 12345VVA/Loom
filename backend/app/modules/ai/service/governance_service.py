"""AI 治理规则、事件与运行时治理服务。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.ai.model.ai import (
    AiGovernanceEvent,
    AiGovernanceRule,
    AiGovernanceRuleMatchRequest,
    AiModel,
    AiModelCallLog,
    AiModelProfile,
    AiProvider,
    AiRuntimeInvocation,
)
from app.modules.ai.service.utils import _window_bounds
from app.modules.base.service.cache_service import cache_decr, cache_incr
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.notification.model.notification import AudienceRule
from app.modules.notification.service.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AiGovernanceRuleService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiGovernanceRule)

    def _before_add(self, data: dict) -> dict:
        self._ensure_unique_code(data.get("code"))
        self._validate_scope(data)
        return data

    def _before_update(self, data: dict, entity: AiGovernanceRule) -> dict:
        self._ensure_unique_code(data.get("code"), exclude_id=entity.id)
        self._validate_scope(data)
        return data

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        return self._batch_decorate(list(super().list(query, current_user, relations, is_tree, parent_field)))

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = self._batch_decorate(list(result.items))
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._batch_decorate([super().info(id, current_user, relations)])[0]

    def toggle(self, id: int) -> dict:
        rule = self.session.get(AiGovernanceRule, id)
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="治理规则不存在")
        rule.is_active = not rule.is_active
        self.session.add(rule)
        self.session.commit()
        return {"success": True, "status": rule.is_active}

    def match(self, payload: AiGovernanceRuleMatchRequest | dict) -> dict:
        if isinstance(payload, dict):
            payload = AiGovernanceRuleMatchRequest(**payload)
        rules = AiGovernanceService(self.session).match_rules(user_id=payload.user_id, profile_id=payload.profile_id)
        items = [self._finalize_data(rule.model_dump()) for rule in rules]
        return {"count": len(items), "items": self._batch_decorate(items)}

    def _ensure_unique_code(self, code: str | None, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(AiGovernanceRule).where(AiGovernanceRule.code == code)
        if exclude_id is not None:
            statement = statement.where(AiGovernanceRule.id != exclude_id)
        if self.session.exec(statement).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="治理规则编码已存在")

    def _validate_scope(self, data: dict) -> None:
        scope_type = data.get("scope_type") or "global"
        if scope_type == "user" and not data.get("user_id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户规则必须选择用户")
        if scope_type == "profile" and not data.get("profile_id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile 规则必须选择调用配置")

    def _decorate(self, data: dict) -> dict:
        return self._batch_decorate([data])[0]

    def _batch_decorate(self, items: list[dict]) -> list[dict]:
        user_map = _bulk_attr_map(self.session, User, _collect_ids(items, "userId", "user_id"), "username")
        profile_map = _bulk_attr_map(
            self.session, AiModelProfile, _collect_ids(items, "profileId", "profile_id"), "name"
        )
        for d in items:
            uid = d.get("userId") if d.get("userId") is not None else d.get("user_id")
            pid = d.get("profileId") if d.get("profileId") is not None else d.get("profile_id")
            d["username"] = user_map.get(uid)
            d["profileName"] = profile_map.get(pid)
        return items


class AiGovernanceEventService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, AiGovernanceEvent)

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        return self._batch_decorate(list(super().list(query, current_user, relations, is_tree, parent_field)))

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        result = super().page(query, current_user, relations)
        result.items = self._batch_decorate(list(result.items))
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> dict:
        return self._batch_decorate([super().info(id, current_user, relations)])[0]

    def stats(self, days: int = 14) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
        base_filter = AiGovernanceEvent.created_at >= since
        total = int(self.session.exec(select(func.count()).where(base_filter)).one() or 0)
        type_rows = self.session.exec(
            select(AiGovernanceEvent.event_type, func.count().label("cnt"))
            .where(base_filter)
            .group_by(AiGovernanceEvent.event_type)
        ).all()
        metric_rows = self.session.exec(
            select(AiGovernanceEvent.metric, func.count().label("cnt"))
            .where(base_filter)
            .group_by(AiGovernanceEvent.metric)
        ).all()
        by_type = {row[0]: int(row[1]) for row in type_rows}
        by_metric = {row[0]: int(row[1]) for row in metric_rows}
        return {"total": total, "byType": by_type, "byMetric": by_metric}

    def _decorate(self, data: dict) -> dict:
        return self._batch_decorate([data])[0]

    def _batch_decorate(self, items: list[dict]) -> list[dict]:
        rule_map = _bulk_attr_map(self.session, AiGovernanceRule, _collect_ids(items, "ruleId", "rule_id"), "name")
        user_map = _bulk_attr_map(self.session, User, _collect_ids(items, "userId", "user_id"), "username")
        provider_map = _bulk_attr_map(self.session, AiProvider, _collect_ids(items, "providerId", "provider_id"), "name")
        model_map = _bulk_attr_map(self.session, AiModel, _collect_ids(items, "modelId", "model_id"), "name")
        profile_map = _bulk_attr_map(
            self.session, AiModelProfile, _collect_ids(items, "profileId", "profile_id"), "name"
        )
        for d in items:
            rid = d.get("ruleId") if d.get("ruleId") is not None else d.get("rule_id")
            uid = d.get("userId") if d.get("userId") is not None else d.get("user_id")
            pid = d.get("providerId") if d.get("providerId") is not None else d.get("provider_id")
            mid = d.get("modelId") if d.get("modelId") is not None else d.get("model_id")
            pfid = d.get("profileId") if d.get("profileId") is not None else d.get("profile_id")
            d["ruleName"] = rule_map.get(rid)
            d["username"] = user_map.get(uid)
            d["providerName"] = provider_map.get(pid)
            d["modelName"] = model_map.get(mid)
            d["profileName"] = profile_map.get(pfid)
        return items


# 并发计数 Redis key 的兜底 TTL（秒），防止僵尸调用永久占用配额
_CONCURRENT_TTL = 7200


def _collect_ids(items: list[dict], camel: str, snake: str) -> set:
    """从一批 dict 中收集关联 id（兼容 camelCase / snake_case 两种 key）。"""
    ids: set = set()
    for d in items:
        value = d.get(camel)
        if value is None:
            value = d.get(snake)
        if value is not None:
            ids.add(value)
    return ids


def _bulk_attr_map(session: Session, model: Any, ids: set, attr: str) -> dict:
    """一次性按 id 批量加载关联实体的某个属性，返回 id→属性值 映射。"""
    if not ids:
        return {}
    rows = session.exec(select(model).where(model.id.in_(ids))).all()
    return {row.id: getattr(row, attr) for row in rows}


class AiGovernanceBlocked(Exception):
    def __init__(self, message: str, *, metric: str = "request"):
        super().__init__(message)
        self.metric = metric


class AiGovernanceService:
    def __init__(self, session: Session):
        self.session = session

    def match_rules(self, *, user_id: int | None, profile_id: int | None) -> list[AiGovernanceRule]:
        statement = (
            select(AiGovernanceRule)
            .where(
                AiGovernanceRule.is_active == True,  # noqa: E712
                AiGovernanceRule.delete_time == None,  # noqa: E711
            )
            .order_by(AiGovernanceRule.sort_order.desc(), AiGovernanceRule.created_at.desc())
        )
        rows = self.session.exec(statement).all()
        matched: list[AiGovernanceRule] = []
        for rule in rows:
            if rule.scope_type == "global":
                matched.append(rule)
            elif rule.scope_type == "user" and user_id is not None and rule.user_id == user_id:
                matched.append(rule)
            elif rule.scope_type == "profile" and profile_id is not None and rule.profile_id == profile_id:
                matched.append(rule)
        return matched

    def begin(
        self, *, user: User | None, provider: AiProvider, model: AiModel, profile: AiModelProfile
    ) -> AiRuntimeInvocation | None:
        user_id = user.id if user else None
        rules = self.match_rules(user_id=user_id, profile_id=profile.id)
        # 1) 预检 request/token/cost（SQL 窗口聚合）
        for rule in rules:
            self._check_pre_rule(rule, user_id=user_id, provider=provider, model=model, profile=profile)
        # 2) 并发检查：Redis 原子计数，超限回退，通过则保留预占
        concurrent_keys = self._acquire_concurrent(rules, user_id, provider, model, profile)
        invocation = AiRuntimeInvocation(
            invocation_id=str(uuid.uuid4()),
            user_id=user_id,
            provider_id=provider.id,
            model_id=model.id,
            profile_id=profile.id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        invocation._cc_keys = concurrent_keys
        self.session.add(invocation)
        self.session.commit()
        return invocation

    def finish(
        self,
        invocation: AiRuntimeInvocation | None,
        *,
        status_value: str,
        user: User | None,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
        usage: dict[str, Any],
        cost_micro_usd: int,
    ) -> None:
        self._release_concurrent(invocation)
        if invocation:
            invocation.status = "success" if status_value == "success" else "error"
            invocation.finished_at = datetime.now(timezone.utc)
            self.session.add(invocation)
        if status_value == "success":
            self._record_post_events(
                user=user, provider=provider, model=model, profile=profile, usage=usage, cost_micro_usd=cost_micro_usd
            )
        self.session.commit()

    def block_invocation(self, invocation: AiRuntimeInvocation | None) -> None:
        self._release_concurrent(invocation)
        if not invocation:
            return
        invocation.status = "blocked"
        invocation.finished_at = datetime.now(timezone.utc)
        self.session.add(invocation)
        self.session.commit()

    def _acquire_concurrent(
        self,
        rules: list[AiGovernanceRule],
        user_id: int | None,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
    ) -> list[str]:
        """对命中规则做并发预占，返回成功预占的 Redis key 列表。enforce 模式超限会抛 AiGovernanceBlocked。"""
        acquired: list[str] = []
        for rule in rules:
            limit = rule.max_concurrent
            if not limit or limit <= 0:
                continue
            key = self._concurrent_key(rule)
            current = cache_incr(key, ttl_seconds=_CONCURRENT_TTL)
            if current is None:
                # Redis 计数不可靠：fail-open 放行（保持可用性），记录告警便于追溯
                logger.warning("并发计数不可靠（Redis 异常），治理规则 %s 本次放行", rule.name)
                continue
            if current > limit:
                cache_decr(key, ttl_seconds=_CONCURRENT_TTL)
                window_start, window_end = _window_bounds(rule.period)
                message = f"AI 治理规则 {rule.name} 已超出 concurrent 限制: {current}/{limit}"
                notified = (
                    self._notify_once(rule, "concurrent", "blocked", window_start, window_end, message)
                    if rule.notify_enabled
                    else False
                )
                self._event(
                    rule,
                    user_id,
                    profile,
                    model,
                    provider,
                    "blocked",
                    "concurrent",
                    current,
                    limit,
                    window_start,
                    window_end,
                    message,
                    notified,
                )
                if rule.mode == "enforce":
                    for prev_key in acquired:
                        cache_decr(prev_key, ttl_seconds=_CONCURRENT_TTL)
                    raise AiGovernanceBlocked(message, metric="concurrent")
            else:
                acquired.append(key)
                if current == limit:
                    window_start, window_end = _window_bounds(rule.period)
                    message = f"AI 治理规则 {rule.name} 即将达到 concurrent 限制: {current}/{limit}"
                    self._event(
                        rule,
                        user_id,
                        profile,
                        model,
                        provider,
                        "warn",
                        "concurrent",
                        current,
                        limit,
                        window_start,
                        window_end,
                        message,
                        False,
                    )
        return acquired

    def _release_concurrent(self, invocation: AiRuntimeInvocation | None) -> None:
        """释放本次调用预占的并发计数。幂等。"""
        if not invocation:
            return
        keys = getattr(invocation, "_cc_keys", None) or []
        for key in keys:
            cache_decr(key, ttl_seconds=_CONCURRENT_TTL)
        invocation._cc_keys = []

    def _concurrent_key(self, rule: AiGovernanceRule) -> str:
        if rule.scope_type == "user":
            return f"ai:gov:cc:user:{rule.user_id}"
        if rule.scope_type == "profile":
            return f"ai:gov:cc:profile:{rule.profile_id}"
        return "ai:gov:cc:global"

    def _check_pre_rule(
        self,
        rule: AiGovernanceRule,
        *,
        user_id: int | None,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
    ) -> None:
        window_start, window_end = _window_bounds(rule.period)
        checks = [
            (
                "request",
                rule.max_requests,
                self._request_count(rule, user_id, profile.id, window_start, window_end) + 1,
                False,
            ),
            ("token", rule.max_tokens, self._token_sum(rule, user_id, profile.id, window_start, window_end), True),
            (
                "cost",
                rule.max_cost_micro_usd,
                self._cost_sum(rule, user_id, profile.id, window_start, window_end),
                True,
            ),
        ]
        for metric, limit, current, block_at_limit in checks:
            if limit is None or limit <= 0:
                continue
            if current > limit or (block_at_limit and current >= limit):
                message = f"AI 治理规则 {rule.name} 已超出 {metric} 限制: {current}/{limit}"
                notified = (
                    self._notify_once(rule, metric, "blocked", window_start, window_end, message)
                    if rule.notify_enabled
                    else False
                )
                self._event(
                    rule,
                    user_id,
                    profile,
                    model,
                    provider,
                    "blocked",
                    metric,
                    current,
                    limit,
                    window_start,
                    window_end,
                    message,
                    notified,
                )
                if rule.mode == "enforce":
                    raise AiGovernanceBlocked(message, metric=metric)
            elif current == limit:
                message = f"AI 治理规则 {rule.name} 即将达到 {metric} 限制: {current}/{limit}"
                self._event(
                    rule,
                    user_id,
                    profile,
                    model,
                    provider,
                    "warn",
                    metric,
                    current,
                    limit,
                    window_start,
                    window_end,
                    message,
                    False,
                )

    def _record_post_events(
        self,
        *,
        user: User | None,
        provider: AiProvider,
        model: AiModel,
        profile: AiModelProfile,
        usage: dict[str, Any],
        cost_micro_usd: int,
    ) -> None:
        user_id = user.id if user else None
        rules = self.match_rules(user_id=user_id, profile_id=profile.id)
        for rule in rules:
            window_start, window_end = _window_bounds(rule.period)
            token_current = self._token_sum(rule, user_id, profile.id, window_start, window_end) + int(
                usage.get("totalTokens") or 0
            )
            cost_current = self._cost_sum(rule, user_id, profile.id, window_start, window_end) + cost_micro_usd
            for metric, limit, current in (
                ("token", rule.max_tokens, token_current),
                ("cost", rule.max_cost_micro_usd, cost_current),
            ):
                if limit is None or limit <= 0 or current < limit:
                    continue
                event_type = "breach" if current > limit else "warn"
                message = f"AI 治理规则 {rule.name} 已达到 {metric} 限制: {current}/{limit}"
                notified = (
                    self._notify_once(rule, metric, event_type, window_start, window_end, message)
                    if rule.notify_enabled
                    else False
                )
                self._event(
                    rule,
                    user_id,
                    profile,
                    model,
                    provider,
                    event_type,
                    metric,
                    current,
                    limit,
                    window_start,
                    window_end,
                    message,
                    notified,
                )

    def _request_count(
        self, rule: AiGovernanceRule, user_id: int | None, profile_id: int | None, start: datetime, end: datetime
    ) -> int:
        statement = select(func.count(AiModelCallLog.id)).where(
            AiModelCallLog.created_at >= start, AiModelCallLog.created_at < end
        )
        statement = self._apply_rule_filter(statement, rule, user_id, profile_id, AiModelCallLog)
        return int(self.session.exec(statement).one() or 0)

    def _token_sum(
        self, rule: AiGovernanceRule, user_id: int | None, profile_id: int | None, start: datetime, end: datetime
    ) -> int:
        statement = select(func.coalesce(func.sum(AiModelCallLog.total_tokens), 0)).where(
            AiModelCallLog.created_at >= start, AiModelCallLog.created_at < end
        )
        statement = self._apply_rule_filter(statement, rule, user_id, profile_id, AiModelCallLog)
        return int(self.session.exec(statement).one() or 0)

    def _cost_sum(
        self, rule: AiGovernanceRule, user_id: int | None, profile_id: int | None, start: datetime, end: datetime
    ) -> int:
        statement = select(func.coalesce(func.sum(AiModelCallLog.cost_micro_usd), 0)).where(
            AiModelCallLog.created_at >= start, AiModelCallLog.created_at < end
        )
        statement = self._apply_rule_filter(statement, rule, user_id, profile_id, AiModelCallLog)
        return int(self.session.exec(statement).one() or 0)

    def _apply_rule_filter(self, statement, rule: AiGovernanceRule, user_id: int | None, profile_id: int | None, table):
        if rule.scope_type == "user":
            statement = statement.where(table.user_id == rule.user_id)
        elif rule.scope_type == "profile":
            statement = statement.where(table.profile_id == rule.profile_id)
        return statement

    def _event(
        self,
        rule: AiGovernanceRule,
        user_id: int | None,
        profile: AiModelProfile,
        model: AiModel,
        provider: AiProvider,
        event_type: str,
        metric: str,
        current: int,
        limit: int,
        window_start: datetime,
        window_end: datetime,
        message: str,
        notified: bool,
    ) -> None:
        self.session.add(
            AiGovernanceEvent(
                rule_id=rule.id,
                user_id=user_id,
                profile_id=profile.id,
                model_id=model.id,
                provider_id=provider.id,
                event_type=event_type,
                metric=metric,
                current_value=current,
                limit_value=limit,
                window_start=window_start,
                window_end=window_end,
                message=message,
                notified=notified,
            )
        )
        self.session.commit()

    def _notify_once(
        self,
        rule: AiGovernanceRule,
        metric: str,
        event_type: str,
        window_start: datetime,
        window_end: datetime,
        message: str,
    ) -> bool:
        exists = self.session.exec(
            select(AiGovernanceEvent).where(
                AiGovernanceEvent.rule_id == rule.id,
                AiGovernanceEvent.metric == metric,
                AiGovernanceEvent.event_type == event_type,
                AiGovernanceEvent.window_start == window_start,
                AiGovernanceEvent.window_end == window_end,
                AiGovernanceEvent.notified == True,  # noqa: E712
            )
        ).first()
        if exists:
            return False
        try:
            NotificationService(self.session).send_business(
                title="AI 治理告警",
                content=message,
                audience=AudienceRule(all_admins=True),
                source_module="ai",
                business_key=f"{rule.id}:{metric}:{event_type}:{window_start.isoformat()}",
                level="warning" if event_type == "warn" else "error",
                link_url="/ai/governance-event",
            )
            return True
        except Exception:
            return False
