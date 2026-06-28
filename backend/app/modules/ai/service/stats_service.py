"""AI 调用统计服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.modules.ai.model.ai import AiModelCallLog


class AiModelCallStatsService:
    def __init__(self, session: Session):
        self.session = session

    def summary(self, days: int | None = None, group_by: str = "day") -> dict:
        statement = select(AiModelCallLog)
        if days:
            statement = statement.where(
                AiModelCallLog.created_at >= datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
            )
        logs = list(self.session.exec(statement).all())
        total = len(logs)
        success = len([item for item in logs if item.status == "success"])
        errors = len([item for item in logs if item.status != "success"])
        avg_latency = int(sum(item.latency_ms for item in logs) / total) if total else 0
        token_total = sum(item.total_tokens for item in logs)
        cost_total = sum(item.cost_micro_usd or 0 for item in logs)
        groups: dict[str, dict[str, Any]] = {}
        for item in logs:
            if group_by == "user":
                key = f"user:{item.user_id or '-'}"
            elif group_by == "profile":
                key = f"profile:{item.profile_id or '-'}"
            elif group_by == "model":
                key = f"model:{item.model_id or '-'}"
            else:
                key = (item.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
            group = groups.setdefault(
                key,
                {
                    "key": key,
                    "userId": item.user_id,
                    "providerId": item.provider_id,
                    "modelId": item.model_id,
                    "profileId": item.profile_id,
                    "total": 0,
                    "success": 0,
                    "error": 0,
                    "totalTokens": 0,
                    "costMicroUsd": 0,
                    "costUsd": 0,
                    "avgLatencyMs": 0,
                    "_latency": 0,
                },
            )
            group["total"] += 1
            group["success" if item.status == "success" else "error"] += 1
            group["totalTokens"] += item.total_tokens
            group["costMicroUsd"] += item.cost_micro_usd or 0
            group["_latency"] += item.latency_ms
        for group in groups.values():
            group["avgLatencyMs"] = int(group["_latency"] / group["total"]) if group["total"] else 0
            group["costUsd"] = round(group["costMicroUsd"] / 1_000_000, 6)
            group.pop("_latency", None)
        return {
            "total": total,
            "success": success,
            "error": errors,
            "successRate": round(success / total, 4) if total else 0,
            "avgLatencyMs": avg_latency,
            "totalTokens": token_total,
            "costMicroUsd": cost_total,
            "costUsd": round(cost_total / 1_000_000, 6),
            "groups": list(groups.values()),
        }
