"""工作流产物生命周期清理：执行日志过期删除 + offload 载荷孤儿回收 + 终态实例 checkpoint 回收。

与产物落地（artifact_service）配套的生命周期治理，由 Celery 任务
workflow.cleanup.sweep 每日调用。语义约定：
- 一律"先删 DB 行、commit 后再删文件"——文件删除失败留孤儿，由
  sweep_orphan_payloads 下一轮兜底；反之先删文件会产生悬挂 ref（接口 500）。
- 孤儿回收仅支持本地存储后端（S3 无列举接口，跳过并告警）。
- checkpoint 线程回收仅 postgres backend 生效（memory 无 checkpoints 表）；以 checkpoints
  表自身做 EXISTS 半连接标记，已清实例自然出局，免重复扫描、免加列（init_db 无列补列机制）。
- 下游模块持有同前缀载荷时，通过 PAYLOAD_REF_PROVIDERS 注册存活引用
  收集器（eval 在 workflow_eval 包导入时注册），保持下游→上游单向依赖。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_
from sqlmodel import Session, select

from app.core.config import settings
from app.framework.storage import StorageService
from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

logger = logging.getLogger(__name__)

_PAYLOAD_PREFIX = "wf_payload_"
# 载荷写入与 DB 登记之间存在秒级窗口（flush 0.2s + 事务提交），仅回收
# mtime 超过宽限期的文件，彻底规避"刚写入未登记被误删"的竞态
_ORPHAN_GRACE_HOURS = 24
_ORPHAN_MAX_DELETE = 5000
# 单轮 checkpoint 清理失败数上限：超过视为 checkpoint 后端异常，提前收束（下轮兜底）
_CHECKPOINT_MAX_DELETE_FAILURES = 100

# 跨模块扩展点（H4 解耦）：返回额外"仍被存活行引用"的载荷 ref 集合。
# 下游模块（workflow_eval 等）在本模块不感知的前提下注册收集器，
# 避免孤儿清扫误删其存活文件；依赖方向由下游 import 本模块完成注册。
PayloadRefProvider = Callable[[Session], Iterable[str | None]]
PAYLOAD_REF_PROVIDERS: list[PayloadRefProvider] = []


class WorkflowCleanupService:
    def __init__(self, session: Session):
        self.session = session

    def sweep_execution_logs(self, keep_days: int, test_node_keep_days: int | None = None, batch_size: int = 500) -> int:
        """分批硬删过期执行日志，返回删除行数；删行后 best-effort 删除其载荷文件。

        test_node_keep_days：单节点测试日志的独立短保留期（开发期高频操作，载荷大、
        追溯价值衰减快），按实例 run_type='test_node' 经 EXISTS 半连接识别；缺省不启用。
        """
        from app.framework.storage import StorageService as _Storage

        cutoff = datetime.now(UTC) - timedelta(days=max(1, int(keep_days)))
        test_cutoff = (
            datetime.now(UTC) - timedelta(days=max(1, int(test_node_keep_days)))
            if test_node_keep_days is not None
            else None
        )
        stale_test_filter = None
        if test_cutoff is not None:
            test_instance = select(WorkflowInstance.id).where(
                WorkflowInstance.id == WorkflowExecutionLog.instance_id,
                WorkflowInstance.run_type == "test_node",
            )
            stale_test_filter = and_(WorkflowExecutionLog.created_at < test_cutoff, test_instance.exists())
        storage = _Storage.get_instance()
        removed = 0
        while True:
            conditions = [
                WorkflowExecutionLog.created_at < cutoff,
                WorkflowExecutionLog.delete_time == None,  # noqa: E711
            ]
            if stale_test_filter is not None:
                conditions.append(stale_test_filter)
            batch = list(
                self.session.exec(
                    select(WorkflowExecutionLog)
                    .where(*conditions)
                    .order_by(WorkflowExecutionLog.id)
                    .limit(batch_size)
                ).all()
            )
            if not batch:
                break
            refs = [ref for log in batch for ref in (log.input_storage_ref, log.output_storage_ref) if ref]
            for log in batch:
                self.session.delete(log)
            self.session.commit()
            removed += len(batch)
            for ref in refs:
                try:
                    storage.delete(ref)
                except Exception:
                    logger.warning("执行日志载荷文件删除失败 ref=%s", ref, exc_info=True)
            if len(batch) < batch_size:
                break
        if removed:
            logger.info("执行日志清理完成 keep_days=%s removed=%d", keep_days, removed)
        return removed

    def sweep_orphan_payloads(
        self, grace_hours: int = _ORPHAN_GRACE_HOURS, max_delete: int = _ORPHAN_MAX_DELETE
    ) -> int:
        """回收无任何 DB 登记的 offload 载荷文件（仅本地存储后端），返回删除文件数。"""

        provider = StorageService.get_instance().provider
        from app.framework.storage import LocalStorageProvider

        if not isinstance(provider, LocalStorageProvider):
            logger.warning("非本地存储后端，跳过孤儿载荷清理")
            return 0

        alive = self._alive_payload_refs()
        upload_dir = provider.upload_dir
        cutoff = datetime.now().timestamp() - max(1, int(grace_hours)) * 3600
        removed = 0
        for root, _dirs, files in os.walk(str(upload_dir)):
            for name in files:
                if not name.startswith(_PAYLOAD_PREFIX) or removed >= max_delete:
                    continue
                full_path = os.path.join(root, name)
                try:
                    if os.path.getmtime(full_path) > cutoff:
                        continue
                except OSError:
                    continue
                rel_dir = os.path.relpath(root, str(upload_dir)).replace(os.sep, "/")
                ref = f"/uploads/{name}" if rel_dir == "." else f"/uploads/{rel_dir}/{name}"
                if ref in alive:
                    continue
                try:
                    os.remove(full_path)
                    removed += 1
                except OSError:
                    logger.warning("孤儿载荷文件删除失败 path=%s", full_path, exc_info=True)
        if removed:
            logger.info("孤儿载荷清理完成 removed=%d", removed)
        return removed

    # 可回收 checkpoint 的终态集合：running/paused 依赖断点恢复，绝不纳入
    _CHECKPOINT_SWEEP_STATUSES = ("success", "failed", "cancelled")

    def sweep_checkpoint_threads(self, keep_days: int, batch_size: int = 500, max_instances: int = 5000) -> int:
        """回收终态实例滞留的 LangGraph checkpoint（checkpoints/blobs/writes 三表），返回清理线程数。

        - 时间判定用 created_at（updated_at 不被 bulk CAS 更新，不可靠）；
        - "是否已清"以 checkpoints 表自身做 EXISTS 半连接标记：删过的 thread 自然出局；
        - 删除失败（best-effort）的 thread 本轮排除，避免阻塞同批后续实例；失败数超
          _CHECKPOINT_MAX_DELETE_FAILURES 视为 checkpoint 后端异常，提前收束（下轮兜底）；
        - memory backend 下 checkpoints 表不存在，直接跳过。
        """
        backend = (settings.WORKFLOW_CHECKPOINT_BACKEND or "memory").strip().lower()
        if backend != "postgres":
            return 0

        from sqlalchemy import column, table

        from app.modules.workflow.service.checkpointer import delete_thread_best_effort

        # checkpoints 表不在 SQLModel metadata，用 Core 轻量表构造参与子查询（不注册、不建表）
        cp = table("checkpoints", column("thread_id"))
        cutoff = datetime.now(UTC) - timedelta(days=max(1, int(keep_days)))
        excluded: list[str] = []
        removed = 0
        while removed < max_instances:
            stmt = select(WorkflowInstance.id, WorkflowInstance.thread_id).where(
                WorkflowInstance.status.in_(self._CHECKPOINT_SWEEP_STATUSES),
                WorkflowInstance.created_at < cutoff,
                WorkflowInstance.thread_id.in_(select(cp.c.thread_id)),
            )
            if excluded:
                stmt = stmt.where(WorkflowInstance.thread_id.not_in(excluded))
            rows = list(
                self.session.exec(
                    stmt.order_by(WorkflowInstance.id).limit(min(batch_size, max_instances - removed))
                ).all()
            )
            if not rows:
                break
            for _iid, thread_id in rows:
                if delete_thread_best_effort(thread_id):
                    removed += 1
                else:
                    excluded.append(thread_id)
                    if len(excluded) >= _CHECKPOINT_MAX_DELETE_FAILURES:
                        logger.warning(
                            "checkpoint 清理失败数达上限 %d，本轮提前收束 removed=%d",
                            _CHECKPOINT_MAX_DELETE_FAILURES,
                            removed,
                        )
                        return removed
        if removed:
            logger.info("checkpoint 线程清理完成 keep_days=%s removed=%d", keep_days, removed)
        return removed

    def _alive_payload_refs(self) -> set[str]:
        """全库仍被存活行引用的载荷 ref 集合（软删行的 ref 视为可回收）。"""
        refs: set[str] = set()

        for state_ref in self.session.exec(
            select(WorkflowInstance.state_data_ref).where(
                WorkflowInstance.delete_time == None,  # noqa: E711
                WorkflowInstance.state_data_ref != None,  # noqa: E711
            )
        ).all():
            refs.add(state_ref)

        for input_ref, output_ref in self.session.exec(
            select(WorkflowExecutionLog.input_storage_ref, WorkflowExecutionLog.output_storage_ref).where(
                WorkflowExecutionLog.delete_time == None  # noqa: E711
            )
        ).all():
            if input_ref:
                refs.add(input_ref)
            if output_ref:
                refs.add(output_ref)

        for content_ref in self.session.exec(
            select(WorkflowArtifact.content_ref).where(
                WorkflowArtifact.delete_time == None,  # noqa: E711
                WorkflowArtifact.content_ref != None,  # noqa: E711
            )
        ).all():
            refs.add(content_ref)

        # 下游模块注册的存活引用（如 workflow_eval 的 case 产物），收集器
        # 抛异常只告警不阻断清扫——单一下游故障不应停摆整条清理链路
        for provider in PAYLOAD_REF_PROVIDERS:
            try:
                for ref in provider(self.session):
                    if ref:
                        refs.add(ref)
            except Exception:
                logger.warning("载荷引用收集器执行失败 provider=%r", provider, exc_info=True)

        return refs
