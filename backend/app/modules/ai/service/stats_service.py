"""AI 调用统计服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlmodel import Session

from app.modules.ai.model.ai import AiModelCallLog
from app.modules.base.service.cache_service import CacheNamespace

# 统计结果缓存命名空间：看板数据可容忍短时延迟，TTL 90s；写调用日志后主动失效（见 invalidate_summary_cache）。
STATS_CACHE = CacheNamespace("ai:stats", default_ttl_seconds=90)

_SUCCESS_CASE = case((AiModelCallLog.status == "success", 1), else_=0)
_ERROR_CASE = case((AiModelCallLog.status != "success", 1), else_=0)


def invalidate_summary_cache() -> None:
    """失效统计看板缓存。在 AiModelCallLog 写入成功后调用。"""
    STATS_CACHE.clear("summary")


def _normalize_group_key(value: Any) -> str:
    """归一化分组键为字符串（兼容 SQLite func.date 返回 str、PG 返回 date 对象）。"""
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class AiModelCallStatsService:
    def __init__(self, session: Session):
        self.session = session

    def summary(self, days: int | None = None, group_by: str = "day") -> dict:
        # 缓存命中优先：看板高频访问，聚合结果可容忍 90s 延迟
        cache_key = ("summary", f"d{days}", group_by)
        cached = STATS_CACHE.get_json(*cache_key)
        if cached is not None:
            return cached

        result = self._aggregate(days, group_by)
        STATS_CACHE.set_json(*cache_key, value=result)
        return result

    def _aggregate(self, days: int | None, group_by: str) -> dict:
        base_filters: list = []
        if days:
            since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
            base_filters.append(AiModelCallLog.created_at >= since)

        # 全局总量与指标：单次 SQL 聚合（替代原全表 load + Python 求和）
        totals_row = self.session.exec(
            select(
                func.count().label("total"),
                func.sum(_SUCCESS_CASE).label("success"),
                func.sum(_ERROR_CASE).label("error"),
                func.avg(AiModelCallLog.latency_ms).label("avg_latency"),
                func.sum(AiModelCallLog.total_tokens).label("total_tokens"),
                func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)).label("cost_micro_usd"),
            ).where(*base_filters)
        ).one()

        total = totals_row.total or 0
        success = totals_row.success or 0
        errors = totals_row.error or 0
        avg_latency = int(totals_row.avg_latency) if totals_row.avg_latency is not None else 0
        token_total = totals_row.total_tokens or 0
        cost_total = totals_row.cost_micro_usd or 0

        return {
            "total": total,
            "success": success,
            "error": errors,
            "successRate": round(success / total, 4) if total else 0,
            "avgLatencyMs": avg_latency,
            "totalTokens": token_total,
            "costMicroUsd": cost_total,
            "costUsd": round(cost_total / 1_000_000, 6),
            "groups": self._grouped(base_filters, group_by),
        }

    def _grouped(self, base_filters: list, group_by: str) -> list[dict]:
        # 选择分组列：func.date 两端通用（SQLite 返回 'YYYY-MM-DD' 字符串，PG 返回 date 对象）
        if group_by == "user":
            group_col = AiModelCallLog.user_id
        elif group_by == "profile":
            group_col = AiModelCallLog.profile_id
        elif group_by == "model":
            group_col = AiModelCallLog.model_id
        else:  # day
            group_col = func.date(AiModelCallLog.created_at)

        stmt = (
            select(
                group_col.label("gkey"),
                func.count().label("total"),
                func.sum(_SUCCESS_CASE).label("success"),
                func.sum(_ERROR_CASE).label("error"),
                func.avg(AiModelCallLog.latency_ms).label("avg_latency"),
                func.sum(AiModelCallLog.total_tokens).label("total_tokens"),
                func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)).label("cost_micro_usd"),
            )
            .where(*base_filters)
            .group_by(group_col)
        )
        rows = self.session.exec(stmt).all()

        groups: list[dict] = []
        for row in rows:
            gkey_raw = row.gkey
            gcost = row.cost_micro_usd or 0
            if group_by == "user":
                key = f"user:{gkey_raw if gkey_raw is not None else '-'}"
            elif group_by == "profile":
                key = f"profile:{gkey_raw if gkey_raw is not None else '-'}"
            elif group_by == "model":
                key = f"model:{gkey_raw if gkey_raw is not None else '-'}"
            else:
                key = _normalize_group_key(gkey_raw)
            groups.append(
                {
                    "key": key,
                    "userId": gkey_raw if group_by == "user" else None,
                    "providerId": None,
                    "modelId": gkey_raw if group_by == "model" else None,
                    "profileId": gkey_raw if group_by == "profile" else None,
                    "total": row.total or 0,
                    "success": row.success or 0,
                    "error": row.error or 0,
                    "totalTokens": row.total_tokens or 0,
                    "costMicroUsd": gcost,
                    "costUsd": round(gcost / 1_000_000, 6),
                    "avgLatencyMs": int(row.avg_latency) if row.avg_latency is not None else 0,
                }
            )
        return groups
