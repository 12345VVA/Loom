"""智能体（AgentProfile）CRUD 服务：编号自动生成 / 可见性过滤 / 状态字段保护。

权限口径（设计 3.6 + 需求 Q2）：全员可建；管理面 draft 仅创建者可见（管理员全量）；
publish/rollback/delete 为「创建者或管理员」（P4 落地，本文件先承载 CRUD 骨架）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_PUBLISH_ACTION_PUBLISH,
    AGENT_PUBLISH_ACTION_ROLLBACK,
    AGENT_STATUS_DRAFT,
    AGENT_TOOL_LEVEL_READONLY,
    AgentProfileDraft,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
)
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService

logger = logging.getLogger("agent.profile_service")

# 快照缓存（评审 P0-4）：按不可变 snapshot_id 缓存、内容永不失效；TTL 60s 仅为兜底
# （快照内容不可变，短 TTL 只影响命中率，无正确性问题）；isCurrent record 实时查库不缓存。
SNAPSHOT_CACHE_TTL_SECONDS = 60
SNAPSHOT_CACHE_PREFIX = "agent:snap:"

# 模型窗口严格模式（评审 P1-2 / D15；E15 动态化）：输入预算 + 输出预算 ≤ 解析链最小窗口。
# 一期常数 32000 下限已废弃（非未知模型推导下界）；存量渠道窗口由迁移 0028 数据兜底。
_INPUT_TOKEN_BUDGET = 6000  # 与 memory_service.AGENT_CONTEXT_TOKEN_BUDGET 同源常量（避免循环导入）


def _canonical_json(payload: dict) -> str:
    """快照哈希输入：键排序 + 紧凑分隔符（跨进程稳定）。"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_draft_json(profile: Any) -> str:
    """draft_json 全量冻结载荷（设计 3.2 schema）。"""
    return json.dumps(
        {
            "profile": {
                "code": profile.code,
                "name": profile.name,
                "description": profile.description,
                "modelProfileCode": profile.model_profile_code,
                "systemPrompt": profile.system_prompt,
                "temperature": profile.temperature,
                "maxTokens": profile.max_tokens,
                "maxToolRounds": profile.max_tool_rounds,
                "timeoutSeconds": profile.timeout_seconds,
                "enableMemory": profile.enable_memory,
            },
            "tools": json.loads(profile.tools or "[]"),
        },
        ensure_ascii=False,
    )


def upsert_draft(session: Session, profile: Any) -> AgentProfileDraft:
    """读/建草稿并同步重建 draft_json/draft_hash（评审 P1-1）；仅内容变化递增 draft_version。"""
    draft = session.exec(select(AgentProfileDraft).where(AgentProfileDraft.profile_id == profile.id)).first()
    draft_json = build_draft_json(profile)
    draft_hash = hashlib.sha256(draft_json.encode("utf-8")).hexdigest()
    if draft is None:
        draft = AgentProfileDraft(
            profile_id=profile.id,
            draft_version=1,
            draft_json=draft_json,
            draft_hash=draft_hash,
            synced_at=datetime.now(UTC),
        )
        session.add(draft)
        session.flush()
        return draft
    if draft.draft_hash != draft_hash:
        draft.draft_version = (draft.draft_version or 0) + 1
        draft.draft_json = draft_json
        draft.draft_hash = draft_hash
        draft.synced_at = datetime.now(UTC)
        session.add(draft)
        session.flush()
    return draft


def _is_super_admin(current_user: User | None) -> bool:
    """与 asset/workflow_eval 同款防御取值。"""
    return bool(current_user is not None and getattr(current_user, "is_super_admin", False))


def resolve_context_window_min(session: Session, model_profile_code: str) -> int | None:
    """解析链最小窗口（E15）：透传 ai 公共查询接口；None = 链上存在未知/不可信候选。"""
    from app.modules.ai.service.registry_service import AiModelRegistryService

    return AiModelRegistryService(session).resolve_context_window(model_profile_code)


def assert_window_for_budget(session: Session, model_profile_code: str, max_tokens: int) -> int:
    """窗口严格校验（发布与 run 发起共用，E15 规则 1/2）：
    解析链最小窗口未知 → 拒绝（不假设 ≥32k）；输入+输出预算超链最小窗口 → 拒绝。
    通过时返回链最小窗口（供动态上下文预算与运行时回退约束复用）。"""
    chain_min = resolve_context_window_min(session, model_profile_code)
    if chain_min is None:
        raise HTTPException(
            status_code=400,
            detail="渠道解析链存在未知窗口的模型（请在 ai 模型管理录入经验证的上下文窗口），未知窗口不放行（E15）",
        )
    needed = _INPUT_TOKEN_BUDGET + int(max_tokens or 0)
    if needed > chain_min:
        raise HTTPException(
            status_code=400,
            detail=f"输入预算 {_INPUT_TOKEN_BUDGET} + 输出上限 {max_tokens} = {needed} tokens，"
            f"超过解析链最小窗口 {chain_min}，请调低输出上限或更换渠道",
        )
    return chain_min


class AgentProfileService(BaseAdminCrudService):
    """agent_profile 活表 CRUD；draft/snapshot/publish 见 profile_service 同文件的发布段（P4）。"""

    def __init__(self, session: Session, model: type = None):  # type: ignore[assignment]
        from app.modules.agent.model.agent import AgentProfile

        super().__init__(session, model or AgentProfile)

    # --- CRUD 生命周期 ---

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增：强制 draft + 创建者；code 留空自动生成 ag-{8位base36}（照 asset 先例）。"""
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)
        data.pop("created_by", None)
        data.pop("enabled", None)  # 启停只经 toggleEnabled
        data["status"] = AGENT_STATUS_DRAFT
        if current_user is not None:
            data["created_by"] = current_user.id
        tools = data.get("tools")
        data["tools"] = json.dumps(tools, ensure_ascii=False) if tools else None
        if not str(data.get("code") or "").strip():
            data["code"] = self._generate_code()
        else:
            data["code"] = str(data["code"]).strip()
            self._assert_code_available(data["code"])
        entity = super().add(data)
        upsert_draft(self.session, entity)  # 同步建草稿：调试台永远最新（评审 P1-1）
        return entity

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新：状态/归属/启停字段剔除（status 只经 publish、enabled 只经 toggleEnabled）。"""
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
        data.pop("status", None)
        data.pop("created_by", None)
        data.pop("enabled", None)
        if "code" in data:
            self._assert_code_available(data.get("code"), exclude_id=data.get("id"))
        if "tools" in data:
            tools = data.get("tools")
            data["tools"] = json.dumps(tools, ensure_ascii=False) if tools else None
        entity = super().update(data)
        if entity is not None:
            refreshed = self.session.get(self.model, entity.id)
            if refreshed is not None:
                upsert_draft(self.session, refreshed)
        return entity

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """软删：仅创建者或管理员。"""
        if current_user is not None and ids:
            for entity in self.session.exec(select(self.model).where(self.model.id.in_(ids))).all():
                if not _is_super_admin(current_user) and entity.created_by != current_user.id:
                    raise HTTPException(status_code=403, detail="仅创建者或管理员可删除该智能体")
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    # --- 可见性过滤（draft 仅创建者可见，管理员全量）---

    def _apply_query(self, statement, model, query, current_user=None, **kwargs):
        statement = super()._apply_query(statement, model, query, current_user, **kwargs)
        if current_user is not None and not _is_super_admin(current_user):
            statement = statement.where(or_(model.status != AGENT_STATUS_DRAFT, model.created_by == current_user.id))
        return statement

    # --- 出口：tools JSON 还原数组 ---

    def _finalize_data(self, data: Any) -> Any:
        rows = data if isinstance(data, list) else [data]
        for item in rows:
            if isinstance(item, dict) and isinstance(item.get("tools"), str):
                item["tools"] = json.loads(item["tools"]) if item["tools"].strip() else []
        return super()._finalize_data(data)

    # --- code 唯一性 ---

    def _generate_code(self) -> str:
        """编号自动生成：ag-{8位随机base36}；冲突重试 3 次，partial unique 兜底并发。"""
        import secrets

        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        for _ in range(3):
            candidate = "ag-" + "".join(secrets.choice(alphabet) for _ in range(8))
            if self._code_free(candidate):
                return candidate
        raise HTTPException(status_code=500, detail="标识生成冲突，请重试")

    def _code_free(self, code: str) -> bool:
        statement = select(self.model).where(
            self.model.code == code,
            self.model.delete_time == None,  # noqa: E711
        )
        return self.session.exec(statement).first() is None

    def _assert_code_available(self, code: Any, exclude_id: int | None = None) -> None:
        if not code:
            return
        statement = select(self.model).where(
            self.model.code == code,
            self.model.delete_time == None,  # noqa: E711
        )
        if exclude_id is not None:
            statement = statement.where(self.model.id != exclude_id)
        if self.session.exec(statement).first() is not None:
            raise HTTPException(status_code=400, detail=f"标识「{code}」已存在")

    # --- 发布快照体系（设计 3.5，D13；锁前移四步）---

    def _assert_manager_or_403(self, entity: Any, current_user: User | None, *, action: str) -> None:
        """操作权（publish/rollback/toggleEnabled/delete）：创建者或管理员。"""
        if current_user is None:
            raise HTTPException(status_code=401, detail="未登录")
        if entity.created_by != current_user.id and not _is_super_admin(current_user):
            raise HTTPException(status_code=403, detail=f"仅创建者或管理员可{action}")

    def _build_publish_payload(self, profile: Any) -> dict:
        """组装发布载荷（评审 P0-6 最小权限边界）：以草稿 tools 名单为起点，逐工具过
        允许列表 + 已注册 + 资源层启用；toolResourceSnapshots 仅含绑定工具。"""
        from app.modules.agent.model.agent import AgentToolResource
        from app.modules.agent.service.runtime import prompt_render
        from app.modules.agent.service.tool_registry import RUNTIME_ALLOWED_TOOLS, get_tool

        tool_names = json.loads(profile.tools or "[]")
        if not tool_names:
            raise HTTPException(status_code=400, detail="发布校验失败：至少绑定一个工具")
        resource_snapshots = []
        for name in tool_names:
            if name not in RUNTIME_ALLOWED_TOOLS:
                raise HTTPException(status_code=400, detail=f"发布校验失败：工具 {name} 不在运行时允许列表内")
            tool = get_tool(name)
            if tool is None:
                raise HTTPException(status_code=400, detail=f"发布校验失败：工具 {name} 未注册（可能已下线）")
            row = self.session.exec(
                select(AgentToolResource).where(
                    AgentToolResource.tool_name == name,
                    AgentToolResource.delete_time == None,  # noqa: E711
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=400, detail=f"发布校验失败：工具 {name} 缺少资源层记录，请先刷新工具")
            if not row.status:
                raise HTTPException(status_code=400, detail=f"发布校验失败：工具 {name} 已被禁用，无法发布")
            if tool.level != AGENT_TOOL_LEVEL_READONLY:
                raise HTTPException(
                    status_code=400, detail=f"发布校验失败：首版仅允许只读工具（D11），{name} 为 {tool.level}"
                )
            resource_snapshots.append(
                {
                    "toolName": name,
                    "displayName": row.display_name or name,
                    "description": tool.description,
                    "level": tool.level,
                    "parameters": tool.parameters,
                }
            )
        return {
            "profile": {
                "code": profile.code,
                "name": profile.name,
                "description": profile.description,
                "systemPrompt": profile.system_prompt,
                "temperature": profile.temperature,
                "maxTokens": profile.max_tokens,
                "maxToolRounds": profile.max_tool_rounds,
                "timeoutSeconds": profile.timeout_seconds,
                "enableMemory": profile.enable_memory,
            },
            "modelProfileCode": profile.model_profile_code,
            "tools": tool_names,
            "toolResourceSnapshots": resource_snapshots,
            "guardrailsVersion": prompt_render.guardrails_version(),
        }

    def _validate_window(self, profile: Any) -> None:
        """窗口严格模式（评审 P1-2 / D15；E15 动态化）：输入+输出预算 ≤ 解析链最小窗口；
        未知窗口不放行；每次 run 发起时还会对实际渠道重校验（渠道档案可能发布后被修改）。"""
        assert_window_for_budget(self.session, profile.model_profile_code, int(profile.max_tokens or 0))

    def publish(self, profile_id: int, current_user: User | None = None) -> AgentProfileSnapshot:
        """发布（设计 3.5 四步）：锁前移——读取/组装/校验/写入/切换全程持 profile 行锁。"""
        entity = self.session.get(self.model, profile_id)
        if entity is None or entity.delete_time is not None:
            raise HTTPException(status_code=404, detail="智能体不存在")
        self._assert_manager_or_403(entity, current_user, action="发布该智能体")

        # ① 锁定 profile 行（SQLite 开发库退化为整库锁，可接受 R3；CI/生产 PG 正确）
        profile = self.session.exec(select(self.model).where(self.model.id == profile_id).with_for_update()).one()
        # ② 锁内读取草稿、组装、校验、哈希
        draft = upsert_draft(self.session, profile)
        payload = self._build_publish_payload(profile)
        self._validate_window(profile)
        snapshot_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

        latest = self.session.exec(
            select(AgentProfileSnapshot)
            .where(AgentProfileSnapshot.profile_id == profile_id)
            .order_by(AgentProfileSnapshot.version.desc())  # type: ignore[attr-defined]
        ).first()
        current_record = self._current_record(profile_id)
        if current_record is not None:
            current_snapshot = self.session.get(AgentProfileSnapshot, current_record.snapshot_id)
            if current_snapshot is not None and current_snapshot.snapshot_hash == snapshot_hash:
                return current_snapshot  # 幂等：内容相同不新建版本（评审 v1.4 P1）

        # ③ 写不可变快照 → 先清 is_current 再插入新 record（顺序不可颠倒，设计 3.5）
        snapshot = AgentProfileSnapshot(
            profile_id=profile_id,
            version=(latest.version if latest else 0) + 1,
            source_draft_version=draft.draft_version,
            snapshot_hash=snapshot_hash,
            agent_name=profile.name,
            agent_code=profile.code,
            snapshot_json=json.dumps(payload, ensure_ascii=False),
            created_by=current_user.id if current_user else None,
        )
        self.session.add(snapshot)
        self.session.flush()  # 取 snapshot.id
        if current_record is not None:
            current_record.is_current = False
            self.session.add(current_record)
        record = AgentProfilePublishRecord(
            profile_id=profile_id,
            snapshot_id=snapshot.id,
            action=AGENT_PUBLISH_ACTION_PUBLISH,
            is_current=True,
            operated_by=current_user.id if current_user else None,
            published_at=datetime.now(UTC),
        )
        self.session.add(record)
        # ④ 单事务提交；提交后事务外失效运行时快照缓存
        self.session.commit()
        self._invalidate_snapshot_cache()
        self.session.refresh(snapshot)
        return snapshot

    def rollback(self, profile_id: int, snapshot_id: int, current_user: User | None = None) -> AgentProfileSnapshot:
        """回滚（与发布同构）：不新建快照，切换 is_current 指针到目标快照。"""
        entity = self.session.get(self.model, profile_id)
        if entity is None or entity.delete_time is not None:
            raise HTTPException(status_code=404, detail="智能体不存在")
        self._assert_manager_or_403(entity, current_user, action="回滚该智能体")

        # 持锁查询（回滚全程与发布切换互斥；行内容不需要读出）
        self.session.exec(select(self.model).where(self.model.id == profile_id).with_for_update()).one()
        target = self.session.get(AgentProfileSnapshot, snapshot_id)
        if target is None or target.profile_id != profile_id:
            raise HTTPException(status_code=404, detail="目标快照不存在或不属于该智能体")
        current_record = self._current_record(profile_id)
        if current_record is not None and current_record.snapshot_id == snapshot_id:
            return target  # 已是当前版本，幂等返回

        if current_record is not None:
            current_record.is_current = False
            self.session.add(current_record)
        record = AgentProfilePublishRecord(
            profile_id=profile_id,
            snapshot_id=snapshot_id,
            action=AGENT_PUBLISH_ACTION_ROLLBACK,
            is_current=True,
            rollback_from_snapshot_id=current_record.snapshot_id if current_record else None,
            operated_by=current_user.id if current_user else None,
            published_at=datetime.now(UTC),
        )
        self.session.add(record)
        self.session.commit()
        self._invalidate_snapshot_cache()
        return target

    def toggle_enabled(self, profile_id: int, enabled: bool, current_user: User | None = None) -> Any:
        """独立启停（需求 4.1 / 评审 v1.4）：实时运行控制，不被发布快照冻结。"""
        entity = self.session.get(self.model, profile_id)
        if entity is None or entity.delete_time is not None:
            raise HTTPException(status_code=404, detail="智能体不存在")
        self._assert_manager_or_403(entity, current_user, action="变更该智能体启停状态")
        entity.enabled = bool(enabled)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    # --- 快照解析（评审 P0-4 重写）---

    def _current_record(self, profile_id: int) -> AgentProfilePublishRecord | None:
        """isCurrent record 实时点查（不缓存——可变状态实时读库）。"""
        return self.session.exec(
            select(AgentProfilePublishRecord).where(
                AgentProfilePublishRecord.profile_id == profile_id,
                AgentProfilePublishRecord.is_current == True,  # noqa: E712
                AgentProfilePublishRecord.delete_time == None,  # noqa: E711
            )
        ).first()

    def get_current_snapshot(self, profile_id: int) -> dict | None:
        """当前生效快照载荷：record 实时查 → 快照按不可变 id 缓存永不失效（TTL 仅兜底）。

        新发起的 run 必定拿到最新快照（record 变化即指向新 snapshot_id）；无「删缓存旧值回写」竞态。
        Redis 不可用时 fail-open 直查库（缓存仅性能优化）。
        """
        record = self._current_record(profile_id)
        if record is None:
            return None
        snapshot = self.session.get(AgentProfileSnapshot, record.snapshot_id)
        if snapshot is None:
            return None
        cache_key = f"{SNAPSHOT_CACHE_PREFIX}{record.snapshot_id}"
        try:
            from app.core.redis import redis_client

            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            payload = json.loads(snapshot.snapshot_json or "{}")
            redis_client.setex(cache_key, SNAPSHOT_CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
            return payload
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 —— 缓存层故障不影响快照解析正确性
            logger.warning("快照缓存读写失败，回退直查库", exc_info=True)
            return json.loads(snapshot.snapshot_json or "{}")

    def _invalidate_snapshot_cache(self) -> None:
        """发布/回滚提交后失效全部快照缓存（record 已指向新 id，失效仅为释放旧命中）。"""
        try:
            from app.core.redis import clear_cache_pattern

            clear_cache_pattern(f"{SNAPSHOT_CACHE_PREFIX}*")
        except Exception:  # noqa: BLE001 —— TTL 兜底保证旧缓存不无限期使用
            logger.warning("快照缓存失效失败（TTL 兜底生效中）", exc_info=True)

    def list_snapshots(self, profile_id: int) -> list[AgentProfileSnapshot]:
        return list(
            self.session.exec(
                select(AgentProfileSnapshot)
                .where(AgentProfileSnapshot.profile_id == profile_id)
                .order_by(AgentProfileSnapshot.version.desc())  # type: ignore[attr-defined]
            ).all()
        )
