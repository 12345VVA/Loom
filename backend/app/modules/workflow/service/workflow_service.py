"""
工作流核心管理与运行时服务。
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.authority_service import is_super_admin
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.service.compiler import (
    node_registry,
)
from app.modules.workflow.service.error_format import friendly_error_message
from app.modules.workflow.service.graph_validate import migrate_legacy_tool_nodes

if TYPE_CHECKING:
    from app.modules.workflow.model.workflow import NodeTestResponse

logger = logging.getLogger(__name__)


# --- 节点执行域拆分后的兼容 re-export（外部具名引用与测试锚点保真） ---
# 执行器与 run_ai_* 的真实定义在 node_executors（patch/logger 锚点随迁）；
# import 本模块仍会级联触发 node_registry 注册副作用。
from .llm_io import (  # noqa: F401
    _MAX_JSON_CANDIDATE_ATTEMPTS as _MAX_JSON_CANDIDATE_ATTEMPTS,
)
from .llm_io import (
    _MAX_JSON_RECURSION_FAILURES as _MAX_JSON_RECURSION_FAILURES,
)
from .llm_io import (
    _build_json_desc_recursive as _build_json_desc_recursive,
)
from .llm_io import (
    _build_json_schema_from_fields as _build_json_schema_from_fields,
)
from .llm_io import (
    _build_llm_response_format as _build_llm_response_format,
)
from .llm_io import (
    _extract_first_json as _extract_first_json,
)
from .llm_io import (
    _field_to_schema as _field_to_schema,
)
from .llm_io import (
    _parse_llm_output as _parse_llm_output,
)
from .node_executors import (  # noqa: F401
    _normalize_intent_label as _normalize_intent_label,
)
from .node_executors import (
    _persist_image_to_media as _persist_image_to_media,
)
from .node_executors import (
    _render_output_field_recursive as _render_output_field_recursive,
)
from .node_executors import (
    execute_batch_processor_node as execute_batch_processor_node,
)
from .node_executors import (
    execute_condition_node as execute_condition_node,
)
from .node_executors import (
    execute_end_node as execute_end_node,
)
from .node_executors import (
    execute_human_input_node as execute_human_input_node,
)
from .node_executors import (
    execute_image_generator_node as execute_image_generator_node,
)
from .node_executors import (
    execute_intent_classifier_node as execute_intent_classifier_node,
)
from .node_executors import (
    execute_llm_node as execute_llm_node,
)
from .node_executors import (
    execute_loop_controller_node as execute_loop_controller_node,
)
from .node_executors import (
    execute_switch_node as execute_switch_node,
)
from .node_executors import (
    execute_tool_executor_node as execute_tool_executor_node,
)
from .node_executors import (
    execute_variable_assignment_node as execute_variable_assignment_node,
)
from .node_executors import (
    execute_variable_transform_node as execute_variable_transform_node,
)
from .node_executors import (
    run_ai_chat as run_ai_chat,
)
from .node_executors import (
    run_ai_image as run_ai_image,
)
from .node_executors import (
    tool_file_system as tool_file_system,
)
from .node_executors import (
    tool_mock_weather_api as tool_mock_weather_api,
)
from .node_executors import (
    tool_web_search as tool_web_search,
)

# --- 2. 工作流服务逻辑 ---

# 工作流实例终态：到达后不可再 start/resume/cancel
TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})


def assert_workflow_owner(session: Session, entity: Any, current_user: User | None) -> None:
    """工作流数据所有者校验：超管放行；无用户上下文（内部调用）放行；否则必须为本人。

    用于修复审查报告 S1（IDOR）：防止用户越权读取/操作他人的工作流定义与实例。
    owner_id 为 None 时放行，兼容迁移前的旧数据。
    """
    if current_user is None:
        return
    if is_super_admin(session, current_user):
        return
    owner_id = getattr(entity, "user_id", None)
    if owner_id is not None and owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的工作流")


class WorkflowService(BaseAdminCrudService):
    """
    工作流定义管理与执行服务
    """

    def __init__(self, session: Session):
        super().__init__(session, WorkflowDefinition)

    def _before_add(self, data: dict) -> dict:
        """
        新增前的校验与逻辑
        """
        # 1. 编码：未提供则自动生成（WF+日期+序列）；显式提供则校验唯一
        code = data.get("code")
        if not code:
            data["code"] = self._generate_code()
        else:
            existing = self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.code == code)).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 注：graph_json 已移至版本表，拓扑校验改由 WorkflowVersionService.save_draft 承担
        return data

    def _generate_code(self) -> str:
        """生成唯一工作流编码：WF + YYYYMMDD + 3位当日序列（如 WF20260630001）。

        取当天同前缀已有编码的最大数字序列 +1；DB code 字段 unique 约束兜底并发冲突。
        """
        prefix = "WF" + datetime.now(UTC).strftime("%Y%m%d")
        rows = self.session.exec(
            select(WorkflowDefinition.code).where(WorkflowDefinition.code.like(f"{prefix}%"))
        ).all()
        max_seq = 0
        for c in rows:
            suffix = c[len(prefix) :]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"{prefix}{max_seq + 1:03d}"

    def _before_update(self, data: dict, entity: Any) -> dict:
        """
        为了支持局部更新（如 cl-switch 仅传 id 和 is_active），
        这里过滤掉未传值（即为 None）的字段，并执行唯一性及拓扑 JSON 校验。
        """
        # 1. 唯一性校验
        code = data.get("code")
        if code and code != entity.code:
            existing = self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.code == code)).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 注：graph_json 已移至版本表，update 不再处理 graph；拓扑校验由 save_draft 承担
        # 注意：此处过滤 None 值（即未显式传递的 Optional 字段）是为了在 cl-switch 局部更新
        # （只传递了 id 和 status/is_active 等）场景下，避免将其余未传字段覆盖更新为 Null。
        # 其副作用是无法通过传递 None/Null 的更新请求将某个字段显式清空。
        # 在本模块（WorkflowDefinitionUpdateRequest 中 description/graph_json 等均为 Optional[str] = None）
        # 场景下目前安全，在此保留此注释以提请后续维护注意该局部更新语义。
        return {k: v for k, v in data.items() if v is not None}

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增工作流定义，自动写入创建者 user_id 以支持数据权限隔离（修复 IDOR）。"""
        if isinstance(payload, list):
            return [self.add(item, current_user) for item in payload]
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        if current_user is not None and "user_id" not in data:
            data["user_id"] = current_user.id
        return super().add(data)

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新前校验调用者是否为该工作流定义的所有者（修复 IDOR 越权改）。"""
        id_val = getattr(payload, "id", None)
        entity = self.session.get(self.model, id_val) if id_val is not None else None
        if entity is not None:
            assert_workflow_owner(self.session, entity, current_user)
        return super().update(payload)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前校验调用者是否为每个待删工作流定义的所有者（修复 IDOR 越权删）。"""
        for entity_id in ids or []:
            entity = self.session.get(self.model, entity_id)
            if entity is not None:
                assert_workflow_owner(self.session, entity, current_user)
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    def info(self, id, current_user=None, relations=()):
        """详情额外回填版本字段：currentVersionNo/currentPublishedAt/draftGraphJson。"""
        result = super().info(id, current_user, relations)
        if isinstance(result, dict):
            self._enrich_with_version_info(result)
        return result

    def list(self, query=None, current_user=None, relations=None, is_tree=None, parent_field=None):
        data = super().list(query, current_user, relations, is_tree, parent_field)
        self._enrich_list_with_version(data)
        return data

    def page(self, query, current_user=None, relations=()):
        result = super().page(query, current_user, relations)
        self._enrich_list_with_version(result.items)
        return result

    def _enrich_list_with_version(self, items: list) -> None:
        """列表批量回填 currentVersionNo/currentPublishedAt（一次 IN 查询）。"""
        if not items:
            return
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        vids = {it.get("currentVersionId") for it in items if isinstance(it, dict) and it.get("currentVersionId")}
        if not vids:
            return
        versions = {
            v.id: v
            for v in self.session.exec(
                select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.id.in_(vids))
            ).all()
        }
        for it in items:
            if not isinstance(it, dict):
                continue
            v = versions.get(it.get("currentVersionId"))
            if v:
                it["currentVersionNo"] = v.version_no
                it["currentPublishedAt"] = v.published_at

    def _enrich_with_version_info(self, data: dict) -> None:
        """info 单条回填 currentVersionNo/currentPublishedAt/draftGraphJson。"""
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        cur_vid = data.get("currentVersionId")
        if cur_vid is not None:
            v = self.session.get(WorkflowDefinitionVersion, cur_vid)
            if v:
                data["currentVersionNo"] = v.version_no
                data["currentPublishedAt"] = v.published_at
        draft_vid = data.get("draftVersionId")
        if draft_vid is not None:
            v = self.session.get(WorkflowDefinitionVersion, draft_vid)
            if v:
                # 三期B7（WF-P2-10）：编辑器打开草稿即见迁移后形态（deprecated tool
                # → tool_executor），保存时落库归一，旧图无感升级
                data["draftGraphJson"] = json.dumps(migrate_legacy_tool_nodes(json.loads(v.graph_json)))
                # 草稿乐观锁基线：editor 保存时经 baseUpdatedAt 回传比对
                data["draftUpdatedAt"] = v.updated_at


def _has_resumable_checkpoint(thread_id: str | None) -> bool:
    """failed 实例断点续跑（WF-P2-17）前置检查：thread_id 上是否存在可恢复 checkpoint。

    仅含 interrupt（human_input）节点的图在执行时挂 checkpointer，其断点在失败
    路径不被立即清除（cleanup 仅按到期回收）；无 checkpoint 的 failed（普通节点
    异常/超时）无从续跑。best-effort：checkpointer 访问异常按「无断点」处理
    （拒绝 resume 是安全侧）。memory 后端与 HTTP 进程不共享内存态，天然返回 False。
    """
    if not thread_id:
        return False
    try:
        from app.modules.workflow.service.checkpointer import get_checkpointer

        snapshot = get_checkpointer().get_tuple({"configurable": {"thread_id": thread_id}})
        return snapshot is not None
    except Exception:
        logger.warning("checkpoint 预检失败 thread_id=%s（按无可恢复断点处理）", thread_id, exc_info=True)
        return False


class WorkflowInstanceService(BaseAdminCrudService):
    """
    工作流实例管理服务
    """

    def __init__(self, session: Session):
        super().__init__(session, WorkflowInstance)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前校验调用者是否为每个待删工作流实例的所有者（修复 IDOR 越权删实例）。

        BaseAdminCrudService.delete 按 ids 直接软删除，不走 DataScope，故在此显式逐条校验 owner。
        附带级联（详见 _cascade_delete）：软删执行日志/产物、清空 state_data、commit 后
        best-effort 删 offload 载荷文件；checkpoint thread 仅硬删时当场删（行已物理消失，
        sweep 无法再定位），软删交由每日 sweep 按 workflowCheckpointKeepDays 回收，
        保住"软删期内可恢复"语义。
        ai_model_call_log（成本审计）与 media_asset（用户资产）保留不删。
        """
        for entity_id in ids or []:
            instance = self.session.get(self.model, entity_id)
            if instance is not None:
                assert_workflow_owner(self.session, instance, current_user)
                if instance.status in ("running", "pending"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"实例 {entity_id} 正在运行中，请先取消后再删除",
                    )

        storage_refs, thread_ids = self._cascade_delete(ids or [])

        active_soft_delete = soft_delete if soft_delete is not None else self.soft_delete
        result = super().delete(ids, payload=payload, soft_delete=soft_delete)

        # DB 已提交，文件与 checkpoint 清理失败仅留孤儿（孤儿清理任务兜底），不影响删除结果
        self._delete_storage_refs(storage_refs)
        if not active_soft_delete:
            from app.modules.workflow.service.checkpointer import delete_thread_best_effort

            for thread_id in thread_ids:
                delete_thread_best_effort(thread_id)
        return result

    def _cascade_delete(self, ids: list[int]) -> tuple[list[str], list[str]]:
        """实例删除级联的 DB 部分：软删执行日志与产物、清空实例大字段。

        返回 (storage_refs, thread_ids)，供 super().delete() commit 后做文件/checkpoint 清理。
        """
        from datetime import datetime

        from sqlalchemy import update as sa_update

        from app.modules.workflow.model.workflow_artifact import WorkflowArtifact

        if not ids:
            return [], []
        now = datetime.now(UTC)
        storage_refs: list[str] = []
        thread_ids: list[str] = []

        instances = list(self.session.exec(select(WorkflowInstance).where(WorkflowInstance.id.in_(ids))).all())
        for inst in instances:
            if inst.state_data_ref:
                storage_refs.append(inst.state_data_ref)
            if inst.thread_id:
                thread_ids.append(inst.thread_id)

        logs = list(
            self.session.exec(select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id.in_(ids))).all()
        )
        for log in logs:
            if log.input_storage_ref:
                storage_refs.append(log.input_storage_ref)
            if log.output_storage_ref:
                storage_refs.append(log.output_storage_ref)

        artifacts = list(self.session.exec(select(WorkflowArtifact).where(WorkflowArtifact.instance_id.in_(ids))).all())
        for artifact in artifacts:
            if artifact.content_ref:
                storage_refs.append(artifact.content_ref)

        self.session.execute(
            sa_update(WorkflowExecutionLog)
            .where(WorkflowExecutionLog.instance_id.in_(ids), WorkflowExecutionLog.delete_time == None)  # noqa: E711
            .values(delete_time=now)
        )
        self.session.execute(
            sa_update(WorkflowArtifact)
            .where(WorkflowArtifact.instance_id.in_(ids), WorkflowArtifact.delete_time == None)  # noqa: E711
            .values(delete_time=now)
        )
        self.session.execute(
            sa_update(WorkflowInstance).where(WorkflowInstance.id.in_(ids)).values(state_data="", state_data_ref=None)
        )
        self.session.commit()
        return storage_refs, thread_ids

    def _delete_storage_refs(self, refs: list[str]) -> None:
        """best-effort 删除 offload 载荷文件；失败仅告警（残留由孤儿清理任务回收）。"""
        from app.framework.storage import StorageService

        storage = StorageService.get_instance()
        for ref in refs:
            try:
                storage.delete(ref)
            except Exception:
                logger.warning("实例级联清理载荷文件失败 ref=%s", ref, exc_info=True)

    def info(self, id, current_user=None, relations=()):
        result = super().info(id, current_user, relations)
        if isinstance(result, dict):
            self._resolve_state_data([result])
            self._enrich_version_no([result])
            self._enrich_token_cost([result])
        return result

    def list(self, query=None, current_user=None, relations=None, is_tree=None, parent_field=None):
        # 列表不做 stateData 还原（前端零消费，offload 实例返回空串原样），避免逐行读对象存储
        data = super().list(query, current_user, relations, is_tree, parent_field)
        self._enrich_definition_name(data)
        self._enrich_version_no(data)
        self._enrich_token_cost(data)
        return data

    def page(self, query, current_user=None, relations=()):
        result = super().page(query, current_user, relations)
        self._enrich_definition_name(result.items)
        self._enrich_version_no(result.items)
        self._enrich_token_cost(result.items)
        return result

    def _resolve_state_data(self, items: list) -> None:
        """T8 还原：stateData 超阈值落对象存储时（stateDataRef 非空）读回全量快照回填 stateData。

        载荷文件丢失时降级为空串（不使详情接口 500）；仅 info 调用，列表不还原。
        """
        if not items:
            return
        from app.framework.storage import resolve_payload

        for it in items:
            if not isinstance(it, dict):
                continue
            ref = it.get("stateDataRef")
            if ref:
                try:
                    it["stateData"] = resolve_payload(it.get("stateData") or "", ref)
                except Exception:
                    logger.warning("state_data 载荷还原失败 ref=%s", ref, exc_info=True)
                    it["stateData"] = ""

    def _enrich_definition_name(self, items: list) -> None:
        """回填 definitionName（join 工作流定义表，一次 IN 查询避免 N+1）。"""
        if not items:
            return
        from app.modules.workflow.model.workflow import WorkflowDefinition

        dids = {it.get("definitionId") for it in items if isinstance(it, dict) and it.get("definitionId")}
        if not dids:
            return
        defs = {
            d.id: d.name
            for d in self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.id.in_(dids))).all()
        }
        for it in items:
            if isinstance(it, dict):
                dname = defs.get(it.get("definitionId"))
                if dname is not None:
                    it["definitionName"] = dname

    def _enrich_version_no(self, items: list) -> None:
        """回填 versionNo（join 版本表，一次 IN 查询）。"""
        if not items:
            return
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        vids = {it.get("versionId") for it in items if isinstance(it, dict) and it.get("versionId")}
        if not vids:
            return
        version_nos = {
            v.id: v.version_no
            for v in self.session.exec(
                select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.id.in_(vids))
            ).all()
        }
        for it in items:
            if isinstance(it, dict):
                vno = version_nos.get(it.get("versionId"))
                if vno is not None:
                    it["versionNo"] = vno

    def _enrich_token_cost(self, items: list) -> None:
        """回填 totalTokens/costUsd（按 instance 聚合 AiModelCallLog，一次 group by 避免 N+1）。"""
        if not items:
            return
        from sqlalchemy import func

        from app.modules.ai.model.ai import AiModelCallLog

        instance_ids = [it.get("id") for it in items if isinstance(it, dict) and it.get("id")]
        if not instance_ids:
            return
        rows = self.session.exec(
            select(
                AiModelCallLog.workflow_instance_id,
                func.sum(AiModelCallLog.total_tokens),
                func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)),
            )
            .where(AiModelCallLog.workflow_instance_id.in_(instance_ids))
            .group_by(AiModelCallLog.workflow_instance_id)
        ).all()
        cost_map = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in rows}
        for it in items:
            if not isinstance(it, dict):
                continue
            tokens, cost_micro = cost_map.get(it.get("id")) or (0, 0)
            it["totalTokens"] = tokens
            it["costUsd"] = cost_micro / 1_000_000.0

    def start_instance(
        self, definition_id: int, inputs: dict[str, Any], current_user: User | None = None
    ) -> WorkflowInstance:
        """
        创建一个工作流实例并启动异步执行（正式运行：跑已发布版 current_version_id）。
        """
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition or not definition.is_active:
            raise HTTPException(status_code=404, detail="工作流定义不存在或未启用")
        if definition.current_version_id is None:
            raise HTTPException(status_code=400, detail="该工作流尚未发布任何版本，无法启动实例")
        # 注：start_instance 不校验 definition owner —— 设计上任何用户均可启动已启用的工作流
        # 定义、实例归属启动者；definition 的可见性已由 DataScope 在 page/list/info 限制。
        return self._create_and_dispatch_instance(
            definition, definition.current_version_id, inputs, current_user, dedup=True
        )

    def start_trial_instance(
        self, definition_id: int, inputs: dict[str, Any], current_user: User | None = None
    ) -> WorkflowInstance:
        """
        试运行实例：跑草稿版（draft_version_id），无草稿回退已发布版。

        与正式 start_instance 分流 —— 编辑器试运行应反映最新保存的草稿，而非上次发布版
        （start_instance 固定走 current_version_id，保存草稿不会改变它，导致试运行跑旧版）。
        不要求已发布（发布前即可试运行）；关闭去重（试运行允许反复触发，前端已防双击）。
        """
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition or not definition.is_active:
            raise HTTPException(status_code=404, detail="工作流定义不存在或未启用")
        draft_vid = definition.draft_version_id or definition.current_version_id
        if draft_vid is None:
            raise HTTPException(status_code=400, detail="该工作流尚无任何版本（草稿/发布），无法试运行")
        return self._create_and_dispatch_instance(
            definition, draft_vid, inputs, current_user, dedup=False, run_type="trial"
        )

    def _create_and_dispatch_instance(
        self,
        definition: WorkflowDefinition,
        version_id: int,
        inputs: dict[str, Any],
        current_user: User | None,
        *,
        dedup: bool = True,
        run_type: str = "production",
    ) -> WorkflowInstance:
        """建实例（绑定指定 version_id）+ 可选防重放去重 + 派发 Celery 执行。

        start_instance（正式，dedup=True）与 start_trial_instance（试运行，dedup=False）共用。
        版本来源由调用方决定：正式走 current_version_id，试运行走草稿。
        run_type 区分正式/试运行（eval 由 workflow_eval 侧自建实例），驱动副作用门控与列表过滤。
        """
        definition_id = definition.id

        # 防重放：优先用 Redis SETNX 抢占式去重锁（覆盖 Celery 多 worker / 高并发盲区，
        # 原 DB 2 秒窗口查询存在竞态）。Redis 不可用时（如本地开发）退回 DB 查询兜底。
        if dedup:
            import hashlib

            dedup_key = (
                f"loom:workflow:start:{definition_id}:"
                f"{hashlib.sha1(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
            )
            try:
                from app.core.redis import redis_client

                if not redis_client.set(dedup_key, "1", nx=True, ex=10):
                    raise HTTPException(status_code=400, detail="检测到重复的启动请求，请稍后再试。")
            except HTTPException:
                raise
            except Exception:
                # Redis 不可用：降级为 DB 2 秒窗口查询兜底，保持与原行为一致，不阻断正常启动
                logger.warning("工作流启动去重锁 Redis 不可用，降级为 DB 查询兜底", exc_info=True)
                two_seconds_ago = datetime.now(UTC) - timedelta(seconds=2)
                stmt = select(WorkflowInstance).where(
                    WorkflowInstance.definition_id == definition_id,
                    # 两段式下排队中的 pending 实例同样是「重复启动」的去重对象
                    WorkflowInstance.status.in_(["running", "pending"]),
                    WorkflowInstance.created_at >= two_seconds_ago,
                )
                for inst in self.session.exec(stmt).all():
                    if inst.state_data == json.dumps(inputs):
                        raise HTTPException(status_code=400, detail="检测到重复的启动请求，请稍后再试。")

        # 初始化实例记录：两段式启动段一——先落 pending（已入队待执行），
        # Celery worker / eval 执行体真正开跑时由 _promote_pending_to_running
        # CAS 提升为 running；队列积压期间列表页如实显示「待运行」。
        thread_id = str(uuid4())
        instance = WorkflowInstance(
            definition_id=definition.id,
            version_id=version_id,
            thread_id=thread_id,
            status="pending",
            state_data=json.dumps(inputs),
            current_node=None,
            user_id=current_user.id if current_user else None,
            run_type=run_type,
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)

        # 通过 Celery 异步任务执行工作流（从 Web 进程剥离至独立 Worker）
        from app.modules.workflow.tasks.workflow_tasks import execute_workflow

        task = execute_workflow.delay(instance.id, definition.id, json.dumps(inputs))
        instance.celery_task_id = task.id
        self.session.add(instance)
        self.session.commit()

        return instance

    def resume_instance(self, instance_id: int, user_input: Any, current_user: User | None = None) -> WorkflowInstance:
        """
        恢复挂起（paused）或失败（failed，有断点前提，WF-P2-17）的工作流实例并传入人类交互值
        """
        instance = self.session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="工作流实例不存在")
        assert_workflow_owner(self.session, instance, current_user)

        # S6 防御：user_input=None 时 json.dumps → "null" → 走 initial_state 从头重跑
        if user_input is None:
            raise HTTPException(status_code=400, detail="恢复值不能为空")
        if instance.status not in ("paused", "failed"):
            raise HTTPException(status_code=400, detail="只有处于挂起或失败状态的工作流实例才可以恢复")

        definition = self.session.get(WorkflowDefinition, instance.definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="关联的工作流定义丢失")

        # WF-P2-17（三期B7）：failed 实例仅当存在可恢复 checkpoint 时允许续跑——
        # 只有含人工审批（interrupt）的图才挂 checkpointer，其断点在失败路径不清除
        # （cleanup 仅按到期回收）；普通节点异常/超时失败的实例无断点可续，引导重跑。
        if instance.status == "failed" and not _has_resumable_checkpoint(instance.thread_id):
            raise HTTPException(
                status_code=409,
                detail="该失败实例没有可恢复的断点（仅人工审批中断会保留断点），请重新运行工作流",
            )

        # S5：原子 CAS 把 paused/failed → running，消除读-校验-写的 TOCTOU 竞态（避免并发 resume 重复扣费）。
        # 三期B7（WF-P2-16）：迁移合法性由 status_flow 表校验
        from app.modules.workflow.service.status_flow import cas_transition

        rowcount = cas_transition(self.session, instance_id, ("paused", "failed"), "running")
        if rowcount == 0:
            # 状态已被其他并发请求改走（恢复/取消/失败），拒绝本次
            self.session.rollback()
            raise HTTPException(status_code=409, detail="实例状态已变更，可能已被其他请求恢复，请刷新后重试")
        self.session.commit()
        self.session.refresh(instance)

        # 通过 Celery 异步任务恢复执行，Command(resume=user_input) 继续
        from app.framework.storage import resolve_payload
        from app.modules.workflow.tasks.workflow_tasks import execute_workflow

        # T8：state_data 可能已超阈值落对象存储（state_data_ref 非空），须还原全量快照再作为初始变量续跑。
        # 注（WF-P2-18）：resume 路径下该快照不参与图执行——LangGraph 从 checkpoint 经
        # Command(resume=…) 恢复状态，checkpoint 丢失时它也无济于事；其唯一作用是作为
        # async_execute 异常兜底路径的 current_vars 初值，供失败节点日志构建。
        initial_state = resolve_payload(instance.state_data, instance.state_data_ref)
        task = execute_workflow.delay(instance.id, definition.id, initial_state, json.dumps(user_input))
        instance.celery_task_id = task.id
        self.session.add(instance)
        self.session.commit()

        return instance

    def cancel_instance(self, instance_id: int, current_user: User | None = None) -> WorkflowInstance:
        """
        主动取消运行中或暂停中的工作流实例（修复审查报告 S4）。
        原子迁移到 cancelled + revoke Celery 任务（强制后背）+ 发布 cancelled 事件。
        """
        instance = self.session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="工作流实例不存在")
        assert_workflow_owner(self.session, instance, current_user)

        if instance.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=400, detail="已结束的实例无法取消")

        # 原子 CAS：仅 running/paused/pending 可取消，避免与 resume/执行循环的并发状态迁移冲突。
        # 三期B7（WF-P2-16）：迁移合法性由 status_flow 表校验
        from app.modules.workflow.service.status_flow import cas_transition

        rowcount = cas_transition(
            self.session,
            instance_id,
            ("running", "paused", "pending"),
            "cancelled",
            extra_values={"error_message": "用户主动取消"},
        )
        if rowcount == 0:
            self.session.rollback()
            raise HTTPException(status_code=409, detail="实例状态已变更，无法取消")
        self.session.commit()
        self.session.refresh(instance)

        # 强制后背：revoke 正在执行的任务（执行主循环同时协作式轮询 status 做优雅退出）
        if instance.celery_task_id:
            from app.celery_app import celery_app

            try:
                celery_app.control.revoke(instance.celery_task_id, terminate=True)
            except Exception:
                logger.warning("revoke 工作流任务失败 instance=%d", instance_id, exc_info=True)

        from app.modules.workflow.service.event_bus import publish_event

        publish_event(instance_id, "cancelled", {"status": "cancelled"})
        return instance

    # ==========================================
    # 节点级运行（开发期调试 / 强一致性）
    # ==========================================

    async def _resolve_node_for_test(
        self,
        definition_id: int,
        node_id: str,
        current_user: User | None,
    ) -> dict[str, Any]:
        """解析待测试节点：校验定义/版本/节点，返回测试上下文。失败抛 HTTPException。

        返回 dict：config（snake_case 节点配置）/ node_type / node_name / version_id（草稿版，
        供测试实例 version_id 回填）。
        """
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
        from app.modules.workflow.service.compiler import (
            CONDITIONAL_NODE_TYPES,
            UNTESTABLE_NODE_TYPES,
            _derive_conditional_config,
            convert_keys_to_snake,
        )

        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="工作流定义不存在")
        assert_workflow_owner(self.session, definition, current_user)

        # 节点测试在 editor 编辑草稿过程中，测草稿版（无草稿回退 current）
        draft_vid = definition.draft_version_id or definition.current_version_id
        if draft_vid is None:
            raise HTTPException(status_code=400, detail="该工作流尚无任何版本，无法测试节点")
        version = self.session.get(WorkflowDefinitionVersion, draft_vid)
        if not version:
            raise HTTPException(status_code=404, detail="版本不存在")
        try:
            # 三期B7（WF-P2-10）：加载入口统一迁移 deprecated tool → tool_executor
            graph_json = migrate_legacy_tool_nodes(json.loads(version.graph_json))
        except Exception:
            raise HTTPException(status_code=400, detail="工作流拓扑解析失败")

        node = next((n for n in graph_json.get("nodes", []) if n.get("id") == node_id), None)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

        node_type = node.get("type")
        # 拦截不可单独测试的节点类型
        if node_type in UNTESTABLE_NODE_TYPES:
            raise HTTPException(status_code=400, detail=f"节点类型 '{node_type}' 不支持单节点测试")

        # 条件节点：与整图编译同源地做边推导（target_route/default_route 写回 config），
        # 否则单测环境拿不到路由，intent 的具名分支在节点测试中恒得 default（WF-P0-1 收尾）
        if node_type in CONDITIONAL_NODE_TYPES:
            config = _derive_conditional_config(node, graph_json.get("edges", []))
        else:
            config = convert_keys_to_snake(node.get("config", {}))
        if not node_registry.get(node_type):
            raise HTTPException(status_code=400, detail=f"工作流中使用了未注册的节点类型: '{node_type}'")
        return {
            "config": config,
            "node_type": node_type,
            "node_name": node.get("name") or node_id,
            "version_id": draft_vid,
        }

    async def test_node(
        self,
        definition_id: int,
        node_id: str,
        mock_variables: dict[str, Any],
        current_user: User | None = None,
    ) -> "NodeTestResponse":
        """
        单节点测试：复用整图执行的节点级语义（入参提炼/自动重试/输出映射，见
        WorkflowCompiler.run_node_standalone），不走完整 LangGraph。

        P1-4 落库：建 run_type='test_node' 实例 + 单行执行日志（脱敏 + 超长 offload），
        结果可追溯/审计并接入运行记录页；响应契约（NodeTestResponse）不变，仅新增 instanceId。
        """
        from app.core.config import settings
        from app.core.redis import redis_client
        from app.modules.workflow.model.workflow import NodeTestResponse
        from app.modules.workflow.service.compiler import WorkflowCompiler

        # 1. 解析节点（校验定义/版本/节点/类型）
        ctx = await self._resolve_node_for_test(definition_id, node_id, current_user)
        config, node_type = ctx["config"], ctx["node_type"]

        # 2. 防重放：同一节点 2 秒内不重复执行 (使用 Redis)
        dedup_key = f"loom:workflow:test_node:{definition_id}:{node_id}"
        if not redis_client.set(dedup_key, "1", nx=True, ex=2):
            raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

        # 3. 建 run_type='test_node' 测试实例（副作用门控按 != production 天然跳过通知/产物）
        instance = WorkflowInstance(
            definition_id=definition_id,
            version_id=ctx["version_id"],
            thread_id=str(uuid4()),
            status="running",
            state_data=json.dumps(mock_variables),
            run_type="test_node",
            user_id=current_user.id if current_user else None,
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)

        # 4. 执行节点（与整图执行共享重试/输出映射 + 超时控制，默认 180 秒；LLM 节点常需 60-180 秒响应）
        timeout_seconds = settings.WORKFLOW_NODE_TEST_TIMEOUT

        start_time = time.perf_counter()
        error_msg = None
        is_timeout = False
        updates = {}
        try:
            updates = await asyncio.wait_for(
                WorkflowCompiler.run_node_standalone(node_id, node_type, config, mock_variables),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            logger.warning("单节点测试超时 [%s] (%ds)", node_id, timeout_seconds)
            error_msg = f"节点执行超时（{timeout_seconds}秒），可能是模型响应过慢或配置有误"
            is_timeout = True
        except Exception as e:
            logger.error("单节点测试执行失败 [%s]: %s", node_id, e, exc_info=True)
            error_msg = friendly_error_message(e)
            is_timeout = False

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # 5. 终态 + 单行执行日志（best-effort：落库失败不影响测试响应）
        try:
            status = "error" if error_msg else "success"
            input_data, input_ref = _test_node_log_payload(mock_variables)
            output_data, output_ref = _test_node_log_payload(updates if not error_msg else {"error": error_msg})
            log_row = WorkflowExecutionLog(
                instance_id=instance.id,
                node_id=node_id,
                node_name=ctx["node_name"][:150],
                node_type=node_type[:50],
                input_data=input_data,
                input_storage_ref=input_ref,
                output_data=output_data,
                output_storage_ref=output_ref,
                latency_ms=latency_ms,
                status=status,
                error_message=error_msg,
            )
            if is_timeout:
                instance.status = "failed"
                instance.error_message = error_msg
            else:
                instance.status = "success" if not error_msg else "failed"
                instance.error_message = error_msg
            self.session.add(instance)
            self.session.add(log_row)
            self.session.commit()
        except Exception:
            logger.warning("单节点测试日志落库失败 instance=%d", instance.id, exc_info=True)

        # 单节点测试主要关心节点本身的输出增量（output_mappings 应用后），不关心完整 variables 状态
        # 三期B6：条件节点的路由器（conditional/intent/switch router）不随最小图执行，
        # 路由决策只能整图试运行验证——测试响应附提示引导
        from app.modules.workflow.service.graph_validate import CONDITIONAL_NODE_TYPES

        hint = None
        if node_type in CONDITIONAL_NODE_TYPES and not error_msg:
            hint = "条件节点的分支路由不随单节点测试执行（执行体仅返回空增量），路由逻辑需整图试运行验证。"
        return NodeTestResponse(
            output=updates,
            latency_ms=latency_ms,
            error=error_msg,
            is_timeout=is_timeout,
            instance_id=instance.id,
            hint=hint,
        )


_TEST_NODE_LOG_INLINE_MAX = 90_000  # 单节点测试日志行内联上限（列宽 100000，留余量）


def _test_node_log_payload(value: Any) -> tuple[str, str | None]:
    """单节点测试日志载荷：脱敏后内联；超长转对象存储 ref（对齐 T8 载荷分离机制）。"""
    from app.framework.storage import offload_payload
    from app.modules.ai.service.security_service import AiSecurityService

    masked = AiSecurityService.mask_sensitive_dict(value) if isinstance(value, dict) else value
    text = json.dumps(masked, ensure_ascii=False, default=str)
    if len(text) <= _TEST_NODE_LOG_INLINE_MAX:
        return text, None
    inline, ref = offload_payload(text)
    # ref 非空表示载荷已落存储：内联留空，读取端 _restore_logs_payload 按 ref 还原
    return ("", ref) if ref else (inline[:_TEST_NODE_LOG_INLINE_MAX], None)


def recover_orphaned_instances(session: Session):
    """
    启动时将长时间卡在 running/pending 状态的实例标记为 failed。
    30 分钟宽限期避免误杀刚启动的正常实例。paused 状态不处理。
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    stmt = select(WorkflowInstance).where(
        WorkflowInstance.status.in_(["running", "pending"]),
        WorkflowInstance.updated_at < cutoff,
    )
    orphaned = list(session.exec(stmt).all())
    if not orphaned:
        return
    for instance in orphaned:
        instance.status = "failed"
        instance.error_message = "Server restarted during workflow execution"
        session.add(instance)
    session.commit()
    logger.warning("已将 %d 个孤儿工作流实例标记为 failed", len(orphaned))
