"""工作流产物生命周期清理：执行日志过期删除 + offload 载荷孤儿回收。

与产物落地（artifact_service）配套的生命周期治理，由 Celery 任务
workflow.cleanup.sweep 每日调用。语义约定：
- 一律"先删 DB 行、commit 后再删文件"——文件删除失败留孤儿，由
  sweep_orphan_payloads 下一轮兜底；反之先删文件会产生悬挂 ref（接口 500）。
- 孤儿回收仅支持本地存储后端（S3 无列举接口，跳过并告警）。
- 下游模块持有同前缀载荷时，通过 PAYLOAD_REF_PROVIDERS 注册存活引用
  收集器（eval 在 workflow_eval 包导入时注册），保持下游→上游单向依赖。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.framework.storage import StorageService
from app.modules.workflow.model.workflow import WorkflowExecutionLog, WorkflowInstance
from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

logger = logging.getLogger(__name__)

_PAYLOAD_PREFIX = "wf_payload_"
# 载荷写入与 DB 登记之间存在秒级窗口（flush 0.2s + 事务提交），仅回收
# mtime 超过宽限期的文件，彻底规避"刚写入未登记被误删"的竞态
_ORPHAN_GRACE_HOURS = 24
_ORPHAN_MAX_DELETE = 5000

# 跨模块扩展点（H4 解耦）：返回额外"仍被存活行引用"的载荷 ref 集合。
# 下游模块（workflow_eval 等）在本模块不感知的前提下注册收集器，
# 避免孤儿清扫误删其存活文件；依赖方向由下游 import 本模块完成注册。
PayloadRefProvider = Callable[[Session], Iterable[str | None]]
PAYLOAD_REF_PROVIDERS: list[PayloadRefProvider] = []


class WorkflowCleanupService:
    def __init__(self, session: Session):
        self.session = session

    def sweep_execution_logs(self, keep_days: int, batch_size: int = 500) -> int:
        """分批硬删过期执行日志，返回删除行数；删行后 best-effort 删除其载荷文件。"""
        from app.framework.storage import StorageService as _Storage

        cutoff = datetime.now(UTC) - timedelta(days=max(1, int(keep_days)))
        storage = _Storage.get_instance()
        removed = 0
        while True:
            batch = list(
                self.session.exec(
                    select(WorkflowExecutionLog)
                    .where(
                        WorkflowExecutionLog.created_at < cutoff,
                        WorkflowExecutionLog.delete_time == None,  # noqa: E711
                    )
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
