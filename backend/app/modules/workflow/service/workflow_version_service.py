"""工作流定义版本服务：草稿保存、发布(CAS)、回滚、版本对比。

纯版本表模型：草稿/发布均为 workflow_definition_version 表的行，靠 status 区分。
- save_draft: 无草稿则建 draft 版本并回填 definition.draft_version_id；有则覆盖草稿 graph_json
- publish: CAS 旧 published→archived、draft→published，主表指针迁移，自动建新草稿（editor 续编）
- rollback: 复制目标历史版本 graph 为新草稿（默认，安全可追溯）；immediate=True 再直接发布
- diff: 两版本 graph 结构对比（nodes/edges added/removed/modified）

自动 page/info/list 经 DataScope 过滤（版本表冗余 user_id = definition owner）。
拓扑校验逻辑迁移自 WorkflowService._before_update。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.workflow.model.workflow import WorkflowDefinition
from app.modules.workflow.model.workflow_version import (
    WorkflowDefinitionVersion,
    WorkflowVersionStatus,
)
from app.modules.workflow.service.workflow_service import assert_workflow_owner

logger = logging.getLogger(__name__)


def validate_graph_json(graph_json: str) -> dict:
    """拓扑 JSON 基础校验（迁移自 WorkflowService._before_update）。返回解析后的 dict。"""
    try:
        graph = json.loads(graph_json) if graph_json else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存失败：画布拓扑 JSON 解析失败: {e}")
    if not isinstance(graph, dict) or "nodes" not in graph or "edges" not in graph:
        raise HTTPException(status_code=400, detail="工作流拓扑结构不合法（缺少 nodes/edges）")
    # start 节点若有则必须有出边，否则 langgraph 编译报 "Graph must have an entrypoint"。
    # 不在此强制 start 存在等其他规则（留给执行期 validate_graph 完整校验），以免影响测试用简化拓扑。
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    start_ids = [n.get("id") for n in nodes if n.get("type") == "start" and n.get("id")]
    if start_ids and not any(e.get("source") == start_ids[0] for e in edges):
        raise HTTPException(status_code=400, detail="保存失败：'start' (开始) 节点必须连接到至少一个下游节点。")
    return graph


class WorkflowVersionService(BaseAdminCrudService):
    """工作流版本管理服务。"""

    def __init__(self, session: Session):
        super().__init__(session, WorkflowDefinitionVersion)

    # ---------------------------------- 草稿 ----------------------------------

    def save_draft(
        self,
        definition_id: int,
        graph_json: str,
        *,
        code: str | None = None,
        name: str | None = None,
        description: str | None = None,
        current_user: User | None = None,
    ) -> WorkflowDefinitionVersion:
        """保存草稿（editor 保存入口）。无草稿建 draft 版本；有则覆盖。同步 code/name/description。"""
        definition = self._get_definition_owned(definition_id, current_user)
        validate_graph_json(graph_json)

        # 元数据局部更新（code 改动需校验唯一）
        if code is not None and code != definition.code:
            self._assert_code_unique(code, definition.id)
            definition.code = code
        if name is not None:
            definition.name = name
        if description is not None:
            definition.description = description

        now = datetime.utcnow()
        draft_vid = definition.draft_version_id
        if draft_vid is not None:
            # 覆盖现有草稿 graph（CAS draft→draft，状态异常则 fallback 建新草稿）
            result = self.session.execute(
                update(WorkflowDefinitionVersion)
                .where(
                    WorkflowDefinitionVersion.id == draft_vid,
                    WorkflowDefinitionVersion.status == WorkflowVersionStatus.DRAFT,
                )
                .values(graph_json=graph_json, updated_at=now)
            )
            if result.rowcount == 0:
                draft_vid = None  # 草稿已被并发发布，重建
        if draft_vid is None:
            draft_vid = self._create_draft(definition, graph_json)

        self.session.commit()
        return self.session.get(WorkflowDefinitionVersion, draft_vid)  # type: ignore[return-value]

    # ---------------------------------- 发布 ----------------------------------

    def publish(
        self, definition_id: int, change_note: str | None, current_user: User | None
    ) -> WorkflowDefinitionVersion:
        """草稿→发布（一步上线）。CAS 状态机：旧 published→archived、draft→published、主表指针迁移。

        自动建下一条新草稿（graph 复制自刚发布版），保证 editor 续编顺畅。
        正在运行的实例按其 version_id 继续跑旧版，不受影响。
        """
        definition = self._get_definition_owned(definition_id, current_user)
        draft_vid = definition.draft_version_id
        if draft_vid is None:
            raise HTTPException(status_code=400, detail="没有草稿可发布，请先保存草稿")
        draft = self.session.get(WorkflowDefinitionVersion, draft_vid)
        if not draft or draft.status != WorkflowVersionStatus.DRAFT:
            raise HTTPException(status_code=400, detail="草稿状态异常，请刷新后重试")

        # 发布前对草稿 graph 做基础结构校验（与 save_draft 一致）：堵住 rollback(immediate=True) 等
        # 绕过保存校验的路径把坏图（如 start 无出边）直接上线。完整校验（孤立节点/模型 profile 等）
        # 仍由运行期 compile_graph 负责，以免影响测试用简化拓扑。
        validate_graph_json(draft.graph_json)

        now = datetime.utcnow()
        publisher_id = current_user.id if current_user else None
        draft_graph = draft.graph_json  # 建新草稿用（CAS 后状态会变）

        # 1) 旧 published CAS→archived
        old_pub_vid = definition.current_version_id
        if old_pub_vid is not None:
            self.session.execute(
                update(WorkflowDefinitionVersion)
                .where(
                    WorkflowDefinitionVersion.id == old_pub_vid,
                    WorkflowDefinitionVersion.status == WorkflowVersionStatus.PUBLISHED,
                )
                .values(status=WorkflowVersionStatus.ARCHIVED, updated_at=now)
            )

        # 2) draft CAS→published（rowcount=0 抛 409 并发冲突）
        result = self.session.execute(
            update(WorkflowDefinitionVersion)
            .where(
                WorkflowDefinitionVersion.id == draft_vid,
                WorkflowDefinitionVersion.status == WorkflowVersionStatus.DRAFT,
            )
            .values(
                status=WorkflowVersionStatus.PUBLISHED,
                published_at=now,
                published_by=publisher_id,
                change_note=change_note,
                updated_at=now,
            )
        )
        if result.rowcount == 0:
            self.session.rollback()
            raise HTTPException(status_code=409, detail="草稿状态已变更（可能被并发发布），请刷新后重试")

        # 3) 主表指针迁移：current 指向新发布版，draft 暂置空（随后建新草稿回填）
        self.session.execute(
            update(WorkflowDefinition)
            .where(WorkflowDefinition.id == definition_id)
            .values(current_version_id=draft_vid, draft_version_id=None)
        )
        self.session.commit()

        # 4) 自动建新草稿（graph 复制自刚发布版）
        self.session.refresh(definition)
        new_draft = WorkflowDefinitionVersion(
            definition_id=definition_id,
            version_no=self._next_version_no(definition_id),
            status=WorkflowVersionStatus.DRAFT,
            graph_json=draft_graph,
            parent_version_id=draft_vid,
            user_id=definition.user_id,
        )
        self.session.add(new_draft)
        self.session.flush()
        self.session.execute(
            update(WorkflowDefinition)
            .where(WorkflowDefinition.id == definition_id)
            .values(draft_version_id=new_draft.id)
        )
        self.session.commit()
        return self.session.get(WorkflowDefinitionVersion, draft_vid)  # type: ignore[return-value]

    # ---------------------------------- 回滚 ----------------------------------

    def rollback(
        self,
        definition_id: int,
        target_version_id: int,
        change_note: str | None,
        current_user: User | None,
        immediate: bool = False,
    ) -> dict:
        """回滚：复制目标历史版本 graph 为新草稿（默认，安全可追溯，用户确认后再 publish）。

        immediate=True：草稿就绪后直接 publish 上线。
        """
        definition = self._get_definition_owned(definition_id, current_user)
        target = self.session.get(WorkflowDefinitionVersion, target_version_id)
        if not target or target.definition_id != definition_id:
            raise HTTPException(status_code=404, detail="目标版本不存在")

        now = datetime.utcnow()
        note = change_note or f"回滚自 v{target.version_no}"
        draft_vid = definition.draft_version_id
        if draft_vid is not None:
            self.session.execute(
                update(WorkflowDefinitionVersion)
                .where(
                    WorkflowDefinitionVersion.id == draft_vid,
                    WorkflowDefinitionVersion.status == WorkflowVersionStatus.DRAFT,
                )
                .values(
                    graph_json=target.graph_json,
                    change_note=note,
                    parent_version_id=target.id,
                    updated_at=now,
                )
            )
            self.session.commit()
            self.session.refresh(definition)
        else:
            new_draft = WorkflowDefinitionVersion(
                definition_id=definition_id,
                version_no=self._next_version_no(definition_id),
                status=WorkflowVersionStatus.DRAFT,
                graph_json=target.graph_json,
                change_note=note,
                parent_version_id=target.id,
                user_id=definition.user_id,
            )
            self.session.add(new_draft)
            self.session.flush()
            self.session.execute(
                update(WorkflowDefinition)
                .where(WorkflowDefinition.id == definition_id)
                .values(draft_version_id=new_draft.id)
            )
            self.session.commit()
            self.session.refresh(definition)

        if immediate:
            published = self.publish(definition_id, note, current_user)
            return {"draftVersionId": None, "publishedVersionId": published.id, "immediate": True}
        return {"draftVersionId": definition.draft_version_id, "publishedVersionId": None, "immediate": False}

    # ---------------------------------- diff ----------------------------------

    def diff(self, version_a_id: int, version_b_id: int, current_user: User | None = None) -> dict:
        """两版本 graph 结构 diff（nodes/edges added/removed/modified，同 id config 深比较）。"""
        va = self.session.get(WorkflowDefinitionVersion, version_a_id)
        vb = self.session.get(WorkflowDefinitionVersion, version_b_id)
        for v in (va, vb):
            if not v:
                raise HTTPException(status_code=404, detail="版本不存在")
            assert_workflow_owner(self.session, self.session.get(WorkflowDefinition, v.definition_id), current_user)

        ga = json.loads(va.graph_json) if va.graph_json else {"nodes": [], "edges": []}
        gb = json.loads(vb.graph_json) if vb.graph_json else {"nodes": [], "edges": []}
        nodes_a = {n.get("id"): n for n in ga.get("nodes", [])}
        nodes_b = {n.get("id"): n for n in gb.get("nodes", [])}
        edges_a = {(e.get("source"), e.get("target"), e.get("type")) for e in ga.get("edges", [])}
        edges_b = {(e.get("source"), e.get("target"), e.get("type")) for e in gb.get("edges", [])}

        nodes_modified = [
            {"id": nid, "type": nodes_b[nid].get("type")}
            for nid in (nodes_a.keys() & nodes_b.keys())
            if nodes_a[nid].get("config") != nodes_b[nid].get("config")
        ]
        edge_key = lambda k: {"source": k[0], "target": k[1], "type": k[2]}  # noqa: E731
        return {
            "versionA": {"id": va.id, "versionNo": va.version_no, "status": va.status},
            "versionB": {"id": vb.id, "versionNo": vb.version_no, "status": vb.status},
            "nodesAdded": [self._node_summary(n) for n in nodes_b.values() if n.get("id") not in nodes_a],
            "nodesRemoved": [self._node_summary(n) for n in nodes_a.values() if n.get("id") not in nodes_b],
            "nodesModified": nodes_modified,
            "edgesAdded": [edge_key(k) for k in edges_b - edges_a],
            "edgesRemoved": [edge_key(k) for k in edges_a - edges_b],
        }

    # ---------------------------------- 清理 ----------------------------------

    def sweep_old_archived(self, keep_days: int = 90) -> int:
        """清理过期归档版本：status=archived 且 published_at 早于 keep_days 前，跳过被
        instance/eval_run 引用的版本（保证历史可溯源）。软删（设 delete_time）。返回清理数。

        由 Celery beat 周期调用，兜底版本表无限增长。draft/published 不动（draft 是当前编辑，
        published 靠 publish 自动转 archived）。
        """
        from datetime import datetime, timedelta

        from app.modules.workflow.model.workflow import WorkflowInstance
        from app.modules.workflow_eval.model.eval_run import WorkflowEvalRun

        threshold = datetime.utcnow() - timedelta(days=keep_days)
        # 被引用的 version_id（不可删，否则历史实例/run 无法溯源）
        referenced = set(
            self.session.exec(
                select(WorkflowInstance.version_id).where(WorkflowInstance.version_id.is_not(None))  # noqa: E711
            ).all()
        )
        referenced.update(
            self.session.exec(
                select(WorkflowEvalRun.definition_version_id).where(
                    WorkflowEvalRun.definition_version_id.is_not(None)  # noqa: E711
                )
            ).all()
        )

        stale = list(
            self.session.exec(
                select(WorkflowDefinitionVersion).where(
                    WorkflowDefinitionVersion.status == WorkflowVersionStatus.ARCHIVED,
                    WorkflowDefinitionVersion.delete_time.is_(None),  # noqa: E711
                    WorkflowDefinitionVersion.published_at < threshold,
                )
            ).all()
        )
        now = datetime.utcnow()
        swept = 0
        for v in stale:
            if v.id in referenced:
                continue
            v.delete_time = now
            self.session.add(v)
            swept += 1
        self.session.commit()
        return swept

    # ---------------------------------- 辅助 ----------------------------------

    def _get_definition_owned(self, definition_id: int, current_user: User | None) -> WorkflowDefinition:
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="工作流定义不存在")
        assert_workflow_owner(self.session, definition, current_user)
        return definition

    def _create_draft(self, definition: WorkflowDefinition, graph_json: str) -> int:
        """新建草稿版本并回填 definition.draft_version_id，返回草稿 id。"""
        draft = WorkflowDefinitionVersion(
            definition_id=definition.id,
            version_no=self._next_version_no(definition.id),
            status=WorkflowVersionStatus.DRAFT,
            graph_json=graph_json,
            parent_version_id=definition.current_version_id,
            user_id=definition.user_id,
        )
        self.session.add(draft)
        self.session.flush()
        definition.draft_version_id = draft.id
        return draft.id

    def _assert_code_unique(self, code: str, exclude_id: int) -> None:
        existing = self.session.exec(
            select(WorkflowDefinition).where(
                WorkflowDefinition.code == code, WorkflowDefinition.id != exclude_id
            )
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

    def _next_version_no(self, definition_id: int) -> int:
        max_no = self.session.exec(
            select(func.max(WorkflowDefinitionVersion.version_no)).where(
                WorkflowDefinitionVersion.definition_id == definition_id
            )
        ).one()
        return int(max_no or 0) + 1

    @staticmethod
    def _node_summary(n: dict) -> dict:
        return {"id": n.get("id"), "type": n.get("type"), "name": n.get("name")}
