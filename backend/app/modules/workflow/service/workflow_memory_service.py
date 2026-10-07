"""工作流长期记忆服务：写路径（三级判定 + 并发防重 + 容量保护）、管理页 CRUD、生命周期。

设计文档：docs/工作流长期记忆节点设计方案-2026-10-07.md（v5.2）。
执行器（memory_store）与本服务（管理页 add）共用写入语义；检索（search）随批次 2 落地。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow.model.workflow import WorkflowDefinition
from app.modules.workflow.model.workflow_memory import (
    MemoryEnv,
    MemoryType,
    SourceRunType,
    WorkflowMemory,
)

logger = logging.getLogger(__name__)


# --- 纯函数（执行器/管理页/测试共用） ---


def normalize_for_hash(content: str) -> str:
    """content_hash 计算前的规范化：strip 首尾空白 + 换行符归一（CRLF/CR → LF）。

    仅用于 hash 计算，落库 content 保持原样（渲染产物忠实存储）。规范化判同的
    两次写入以首写为准（设计 §5.3 v5.2）。
    """
    return content.strip().replace("\r\n", "\n").replace("\r", "\n")


def content_hash_of(content: str) -> str:
    return hashlib.sha256(normalize_for_hash(content).encode("utf-8")).hexdigest()


def derive_memory_env(run_type: str) -> str:
    """run_type → memory_env 推导的单一权威（设计 §8）。

    production/trial → production（trial 有意写生产，试运行必须真实反映节点语义）；
    test_node → test（物理隔离）；eval 不会到达此处（store 执行器先行跳过），
    防御性归 production 并告警。
    """
    if run_type == "test_node":
        return MemoryEnv.TEST
    if run_type != "production":
        logger.warning("memory env 推导收到非常规 run_type=%r（eval 应在执行器层被跳过），归 production", run_type)
    return MemoryEnv.PRODUCTION


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _integrity_target(exc: IntegrityError) -> str | None:
    """从 IntegrityError 识别命中的唯一约束（并发防重按冲突目标分流，设计 §4.2）。

    PG：constraint_name 直接可得；SQLite：message 只含列名不含索引名，
    按列集合区分（uq_mem_key 列集含 memory_key，uq_mem_hash 含 content_hash，正交）。
    """
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if name:
        return name
    msg = str(orig)
    if "memory_key" in msg:
        return "uq_mem_key"
    if "content_hash" in msg:
        return "uq_mem_hash"
    return None


def run_ai_embedding(text: str, profile_code: str | None = None) -> tuple[list[float] | None, str | None]:
    """memory 域专属 embedding 封装（设计 §5.4，含 v5.2 失败态）。返回 (vector, space)：

    - ready 态：(vector, "model:dimension")——space 自 resolved["model"].code 推导，
      调用方不自行拼装；
    - 失败态：(None, model_code)——resolve 在调用前完成（code 不依赖调用成败），
      裸 code（无维度段），检索侧 embedding 为 NULL 本就跳过精排，不会被误判可比；
    - 未配置态：(None, None)——无可用 embedding profile（HTTPException 归此态）。

    放本模块而非 node_executors 的「统一 AI 封装区」：管理页 add 与执行器共用，
    避免 service ↔ node_executors 循环导入（见实施方案 §0.3）。
    """
    from app.core.database import SessionLocal
    from app.modules.ai.model.ai import AiEmbeddingRequest
    from app.modules.ai.service.registry_service import AiModelRegistryService
    from app.modules.ai.service.runtime_service import AiModelRuntimeService

    with SessionLocal() as session:
        registry = AiModelRegistryService(session)
        runtime = AiModelRuntimeService(session)
        try:
            resolved = registry.resolve(model_type="embedding", profile_code=profile_code or None)
        except HTTPException:
            # 404 未找到 profile / 400 模型不可用，均归「未配置 embedding」
            return None, None
        model_code = resolved["model"].code
        try:
            result = runtime.embedding(AiEmbeddingRequest(profile_code=profile_code, input=text))
        except Exception:
            logger.warning("记忆向量化调用失败 model=%s（落失败态：space=裸 code）", model_code, exc_info=True)
            return None, model_code
        if not result.get("success"):
            logger.warning(
                "记忆向量化返回失败 model=%s detail=%s", model_code, result.get("errorMessage") or result.get("message")
            )
            return None, model_code
        data = result.get("data") or []
        vector = data[0].get("embedding") if data else None
        if not vector:
            return None, model_code
        return vector, f"{model_code}:{len(vector)}"


# --- 写路径核心 ---


def upsert_memory(
    session: Session,
    *,
    definition_id: int,
    memory_env: str,
    content: str,
    memory_key: str | None,
    memory_type: str,
    tags: list[str],
    embedding: list[float] | None,
    embedding_space: str | None,
    source_instance_id: int | None,
    source_node_id: str | None,
    source_run_type: str,
    user_id: int | None,
) -> tuple[int, str]:
    """写入一条记忆：key upsert → hash 精确去重 → 语义相似 warning（三级判定，设计 §5.3）。

    返回 (memory_id, action)，action ∈ created | updated | deduplicated
    （skipped / degraded 在执行器层产生，不经此函数）。
    并发窗口（设计 §4.2 v5.1）：应用层 SELECT 快路径 + INSERT 捕获 IntegrityError 后
    rollback **重走完整判定**——撞 uq_mem_key 进 UPDATE 分支（后写者 content 胜出，
    不静默丢弃）；撞 uq_mem_hash 返回既有 id。不用 ON CONFLICT（DO UPDATE 内无法执行
    应用层钩子：embedding 重算/语义 warning/action 归因）。
    """
    if memory_type not in MemoryType.ALL:
        raise ValueError(f"memory_type 仅支持 {'/'.join(MemoryType.ALL)}，实际 {memory_type!r}")
    max_len = settings.WORKFLOW_MEMORY_MAX_CONTENT_LENGTH
    if len(content) > max_len:
        raise ValueError(f"记忆内容超长（{len(content)} > {max_len}），不截断直接拒绝")
    content_hash = content_hash_of(content)
    tags_json = json.dumps(tags, ensure_ascii=False)

    # 快路径 SELECT 判重（活跃行）
    existing = _find_existing(session, definition_id, memory_env, memory_key, content_hash)
    if existing is not None:
        if memory_key:
            _apply_key_upsert(
                existing,
                content=content,
                content_hash=content_hash,
                tags_json=tags_json,
                embedding=embedding,
                embedding_space=embedding_space,
                source_instance_id=source_instance_id,
                source_node_id=source_node_id,
                source_run_type=source_run_type,
                user_id=user_id,
            )
            session.commit()
            return existing.id, "updated"
        # 无 key 命中 hash：首写为准，后写丢弃（返回首写 id 供调用方核对）
        return existing.id, "deduplicated"

    if not memory_key:
        _warn_if_similar(session, definition_id, memory_env, embedding, embedding_space)

    row = WorkflowMemory(
        definition_id=definition_id,
        memory_env=memory_env,
        memory_type=memory_type,
        memory_key=memory_key or None,
        content=content,
        content_hash=content_hash,
        tags=tags_json,
        embedding=json.dumps(embedding, ensure_ascii=False) if embedding is not None else None,
        embedding_space=embedding_space,
        source_instance_id=source_instance_id,
        source_node_id=source_node_id,
        source_run_type=source_run_type,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        target = _integrity_target(exc)
        # 慢路径：并发方已提交，此刻 SELECT 必然可见，重走完整判定
        existing = _find_existing(session, definition_id, memory_env, memory_key, content_hash)
        if existing is not None:
            if memory_key:
                _apply_key_upsert(
                    existing,
                    content=content,
                    content_hash=content_hash,
                    tags_json=tags_json,
                    embedding=embedding,
                    embedding_space=embedding_space,
                    source_instance_id=source_instance_id,
                    source_node_id=source_node_id,
                    source_run_type=source_run_type,
                    user_id=user_id,
                )
                session.commit()
                return existing.id, "updated"
            return existing.id, "deduplicated"
        logger.warning("记忆写入唯一约束冲突但重走判定未命中 target=%s definition=%s", target, definition_id)
        raise
    row_id = row.id
    _enforce_scope_cap(session, definition_id, memory_env)
    return row_id, "created"


def _find_existing(
    session: Session, definition_id: int, memory_env: str, memory_key: str | None, content_hash: str
) -> WorkflowMemory | None:
    """快路径判重：有 key 按 (definition, env, key) 查；无 key 按 content_hash 查（活跃行）。"""
    stmt = select(WorkflowMemory).where(
        WorkflowMemory.definition_id == definition_id,
        WorkflowMemory.memory_env == memory_env,
        WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
    )
    if memory_key:
        stmt = stmt.where(WorkflowMemory.memory_key == memory_key)
    else:
        stmt = stmt.where(WorkflowMemory.memory_key.is_(None), WorkflowMemory.content_hash == content_hash)  # type: ignore[attr-defined]
    return session.exec(stmt).first()


def _apply_key_upsert(
    row: WorkflowMemory,
    *,
    content: str,
    content_hash: str,
    tags_json: str,
    embedding: list[float] | None,
    embedding_space: str | None,
    source_instance_id: int | None,
    source_node_id: str | None,
    source_run_type: str,
    user_id: int | None,
) -> None:
    """key upsert 的 UPDATE：content/tags/embedding（重算）+ 刷新 source_*（「当前内容来源」
    语义，与 content 同步更新）+ updated_by（最后写入者）；created_by / created_at 恒不变。"""
    row.content = content
    row.content_hash = content_hash
    row.tags = tags_json
    row.embedding = json.dumps(embedding, ensure_ascii=False) if embedding is not None else None
    row.embedding_space = embedding_space
    row.source_instance_id = source_instance_id
    row.source_node_id = source_node_id
    row.source_run_type = source_run_type
    row.updated_by_user_id = user_id
    # created_by_user_id / created_at 恒不变（最初创建者语义）；commit 由调用方统一执行


def _warn_if_similar(
    session: Session, definition_id: int, memory_env: str, embedding: list[float] | None, embedding_space: str | None
) -> None:
    """三级判定的语义相似提示：仅 warning 不丢弃（8 折 vs 7 折向量高度相似但语义相反，
    按相似丢弃会静默吞新事实）。窗口内无 ready 行直接跳过，零开销退出（§5.3 v5.2）。"""
    if not embedding or not embedding_space or ":" not in embedding_space:
        return
    window = settings.WORKFLOW_MEMORY_DEDUPE_WINDOW
    rows = list(
        session.exec(
            select(WorkflowMemory)
            .where(
                WorkflowMemory.definition_id == definition_id,
                WorkflowMemory.memory_env == memory_env,
                WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
            )
            .order_by(WorkflowMemory.id.desc())
            .limit(window)
        ).all()
    )
    # 仅 ready 态行（embedding 非空 + space 含维度段）参与比对，且 space 一致（同模型同维度才可比）
    threshold = settings.WORKFLOW_MEMORY_DEDUPE_SIMILARITY
    for row in rows:
        if not row.embedding or not row.embedding_space or row.embedding_space != embedding_space:
            continue
        try:
            other = json.loads(row.embedding)
        except (TypeError, ValueError):
            continue
        if _cosine_similarity(embedding, other) >= threshold:
            logger.warning(
                "疑似重复/矛盾记忆写入 definition=%s env=%s space=%s similar_row_id=%d——"
                "如需覆盖请为 memory_store 配置 memoryKeyTemplate（key upsert）",
                definition_id,
                memory_env,
                embedding_space,
                row.id,
            )
            return  # 提示一次即可，不逐行刷屏


def _enforce_scope_cap(session: Session, definition_id: int, memory_env: str) -> None:
    """容量保护（设计 §4.4）：先插后淘——INSERT 提交后计数，超限才软删最旧一批。

    只算活跃行；淘汰走软删（统一入墓碑由 sweep 硬清）；并发容忍短暂超限不加锁
    （cap 是保护机制不是精确配额，加锁会把保护做成串行瓶颈）。
    """
    cap = settings.WORKFLOW_MEMORY_SCOPE_CAP
    active_count = int(
        session.exec(
            select(func.count())
            .select_from(WorkflowMemory)
            .where(
                WorkflowMemory.definition_id == definition_id,
                WorkflowMemory.memory_env == memory_env,
                WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
            )
        ).one()
    )
    if active_count <= cap:
        return
    batch = settings.WORKFLOW_MEMORY_EVICTION_BATCH
    victims = list(
        session.exec(
            select(WorkflowMemory)
            .where(
                WorkflowMemory.definition_id == definition_id,
                WorkflowMemory.memory_env == memory_env,
                WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
            )
            .order_by(
                func.coalesce(WorkflowMemory.last_accessed_at, WorkflowMemory.updated_at, WorkflowMemory.created_at)
            )
            .limit(batch)
        ).all()
    )
    now = datetime.now(UTC)
    for row in victims:
        row.delete_time = now
        session.add(row)
    session.commit()
    logger.warning(
        "记忆容量超限已淘汰 namespace=workflow/%d/%s active=%d cap=%d evicted=%d",
        definition_id,
        memory_env,
        active_count,
        cap,
        len(victims),
    )


# --- 生命周期 ---


def cascade_soft_delete_by_definition(session: Session, definition_id: int) -> int:
    """definition 删除级联：批量软删其全部记忆（设计 §4.4，ownership lifetime 与工作流一致）。

    自治小事务（软删幂等，失败重试安全）；残留墓碑由 sweep 统一硬清。
    """
    now = datetime.now(UTC)
    rows = list(
        session.exec(
            select(WorkflowMemory).where(
                WorkflowMemory.definition_id == definition_id,
                WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
            )
        ).all()
    )
    for row in rows:
        row.delete_time = now
        session.add(row)
    session.commit()
    return len(rows)


def sweep_memory_tombstones(keep_days: int, batch_size: int = 500, session: Session | None = None) -> int:
    """硬删过期软删墓碑（delete_time < now - keep_days），覆盖容量淘汰/手动删/级联删三来源。

    挂 workflow.cleanup.sweep（SysParam workflowMemoryTombstoneKeepDays，默认 90）；
    循环批直至清完。session 缺省时自开独立会话（Celery 上下文），测试可注入。
    """
    cutoff = datetime.now(UTC) - timedelta(days=max(1, int(keep_days)))
    if session is not None:
        return _sweep_tombstones_in_session(session, cutoff, batch_size)
    from app.core.database import SessionLocal

    with SessionLocal() as owned_session:
        return _sweep_tombstones_in_session(owned_session, cutoff, batch_size)


def _sweep_tombstones_in_session(session: Session, cutoff: datetime, batch_size: int) -> int:
    removed_total = 0
    while True:
        rows = list(
            session.exec(
                select(WorkflowMemory)
                .where(
                    WorkflowMemory.delete_time.is_not(None),  # type: ignore[attr-defined]
                    WorkflowMemory.delete_time < cutoff,
                )
                .limit(batch_size)
            ).all()
        )
        if not rows:
            break
        for row in rows:
            session.delete(row)
        session.commit()
        removed_total += len(rows)
    if removed_total:
        logger.info("记忆墓碑清理完成 removed=%d", removed_total)
    return removed_total


# --- 管理页四动作服务（add/delete/page/info；无 update——修正走删旧+新增或 key upsert） ---


def _visible_definition_ids(session: Session, current_user: User) -> set[int] | None:
    """当前用户可见的工作流 definition_id 集合（复用 DataScope 语义对 definition 表过滤）。

    返回 None 表示不过滤（全量数据权限 / 超管）；空集合表示无任何可见工作流。
    """
    from app.framework.router.query_builder import QueryBuilder
    from app.modules.base.service.data_scope_service import resolve_data_scope

    scope = resolve_data_scope(session, current_user)
    if scope is None or scope.allow_all:
        return None
    stmt = QueryBuilder(WorkflowDefinition, None).apply_data_scope(
        select(WorkflowDefinition.id), scope, current_user.id
    )
    return {row[0] for row in session.exec(stmt).all()}


class WorkflowMemoryService(BaseAdminCrudService):
    """记忆管理页服务。管理页写入恒 production env + admin 溯源 + 当前操作者审计。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowMemory)
        self._current_add_user_id: int | None = None

    # 框架按方法签名注入 current_user（_invoke_service 签名过滤）；Base.add 不收，
    # 这里覆盖以捕获操作者，_before_add 无法拿到用户上下文
    def add(self, payload: Any, current_user: User | None = None) -> Any:
        self._current_add_user_id = current_user.id if current_user else None
        try:
            return super().add(payload)
        finally:
            self._current_add_user_id = None

    def _before_add(self, data: dict) -> dict:
        content = data.get("content") or ""
        data["content_hash"] = content_hash_of(content)
        tags = data.get("tags")
        if isinstance(tags, list):
            data["tags"] = json.dumps(tags, ensure_ascii=False)
        data["memory_env"] = MemoryEnv.PRODUCTION  # 管理页手工新增恒生产环境
        data["source_run_type"] = SourceRunType.ADMIN
        user_id = self._current_add_user_id
        data["created_by_user_id"] = user_id
        data["updated_by_user_id"] = user_id
        # embedding 可选（设计 §11）：填 profile 且成功 → ready；失败 → 裸 code 失败态；
        # 不填 → NULL 未配置态（走关键词回退）。管理页 add 保持纯 DB 写入简单性，
        # 不接受请求直塞 embedding 向量
        profile_code = data.pop("embedding_profile_code", None)
        if profile_code:
            vector, space = run_ai_embedding(content, profile_code)
            data["embedding"] = json.dumps(vector, ensure_ascii=False) if vector is not None else None
            data["embedding_space"] = space
        else:
            data.pop("embedding", None)
        return data

    def page(self, query: Any, current_user: User | None = None, relations: tuple = ()) -> Any:
        result = super().page(query, current_user, relations=relations)
        self._enrich_definition_name(result.items)
        return result

    def info(self, id: Any, current_user: User | None = None, relations: tuple = ()) -> Any:
        result = super().info(id, current_user, relations)
        if isinstance(result, dict):
            self._enrich_definition_name([result])
        return result

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前按 definition 归属校验（IDOR 防线；memory 无 user_id 列，DataScope
        对无归属列模型不生效——读路径已在 _apply_query 显式过滤，删除同理显式拦截）。"""
        if current_user is not None and ids and not current_user.is_super_admin:
            rows = list(self.session.exec(select(WorkflowMemory).where(WorkflowMemory.id.in_(ids))).all())
            visible = _visible_definition_ids(self.session, current_user)
            for row in rows:
                if visible is not None and row.definition_id not in visible:
                    raise HTTPException(status_code=403, detail="无权删除非本人工作流的记忆")
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    def _apply_query(self, statement, model, query, current_user=None, fallback_field="created_at", relations=()):
        """读路径按 definition 归属过滤（query_builder 的 DataScope 跳过无 user_id 模型）。"""
        statement = super()._apply_query(statement, model, query, current_user, fallback_field, relations)
        if current_user is not None and not current_user.is_super_admin:
            visible = _visible_definition_ids(self.session, current_user)
            if visible is None:
                return statement
            # 空集合：无任何可见工作流 → 恒假条件返回空集（in_() 空列表在部分方言报错，用恒假等值）
            if not visible:
                return statement.where(WorkflowMemory.id == -1)
            statement = statement.where(WorkflowMemory.definition_id.in_(visible))
        return statement

    def _enrich_definition_name(self, items: list[dict]) -> None:
        """列表/详情回填 definition_name（一次 IN 查询，N+1 禁令）。"""
        def_ids = {it.get("definition_id") for it in items if isinstance(it, dict) and it.get("definition_id")}
        if not def_ids:
            return
        names = {
            d.id: d.name
            for d in self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.id.in_(def_ids))).all()
        }
        for it in items:
            if isinstance(it, dict) and it.get("definition_id") in names:
                it["definition_name"] = names[it["definition_id"]]
