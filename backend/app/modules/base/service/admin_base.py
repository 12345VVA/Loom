"""
管理服务基座：payload 兼容工具、实体 diff 工具与 BaseAdminCrudService。

由 admin_service.py 门面 re-export 供外部引用，外部请勿直接 import 本模块。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.database import transaction
from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.base.model.auth import PageResult, User
from app.modules.base.service.data_scope_service import resolve_data_scope

logger = logging.getLogger(__name__)


def get_request_ip_from_payload(payload: Any = None) -> str | None:
    """从payload中提取IP地址"""
    if payload and hasattr(payload, "_request"):
        request = getattr(payload, "_request", None)
        if request and hasattr(request, "client"):
            return getattr(request.client, "host", None) if request.client else None
    return None


def get_request_ip_from_request(request: Any = None) -> str | None:
    """从Request对象中提取IP地址"""
    if request and hasattr(request, "client"):
        return getattr(request.client, "host", None) if request.client else None
    return None


def get_payload_attr(payload: Any, key: str, default: Any = None) -> Any:
    """兼容从 dict 或 Pydantic/类实例中获取属性"""
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def has_payload_attr(payload: Any, key: str) -> bool:
    """兼容判断 dict 或 Pydantic/类实例是否具有某属性或键"""
    if isinstance(payload, dict):
        return key in payload
    return hasattr(payload, key)


def compute_entity_diff(old_data: dict, new_data: dict, exclude_fields: set = None) -> dict:
    """
    计算实体变更前后的差异

    Args:
        old_data: 变更前的数据字典
        new_data: 变更后的数据字典
        exclude_fields: 要排除的字段集合（如updated_at等自动更新字段）

    Returns:
        变更差异字典，格式：{field: {"old": old_value, "new": new_value}}
    """
    if exclude_fields is None:
        exclude_fields = {"updated_at", "update_time", "modify_time"}

    diff = {}
    all_keys = set(old_data.keys()) | set(new_data.keys())

    for key in all_keys:
        if key in exclude_fields:
            continue

        old_value = old_data.get(key)
        new_value = new_data.get(key)

        # 处理None值和空字符串/零值的比较
        if old_value != new_value:
            # 对于datetime等特殊类型，转换为字符串进行比较
            if hasattr(old_value, "isoformat"):
                old_value = old_value.isoformat()
            if hasattr(new_value, "isoformat"):
                new_value = new_value.isoformat()

            if old_value != new_value:
                diff[key] = {"old": old_value, "new": new_value}

    return diff


def entity_to_dict(entity, exclude_fields: set = None) -> dict:
    """
    将SQLModel实体转换为字典

    Args:
        entity: SQLModel实体实例
        exclude_fields: 要排除的字段集合

    Returns:
        字典表示的实体数据
    """
    if exclude_fields is None:
        exclude_fields = {"password_hash", "delete_time"}

    result = {}
    for key in entity.__dict__.keys():
        if key.startswith("_"):
            continue
        if key in exclude_fields:
            continue

        value = getattr(entity, key, None)
        if value is not None:
            # 处理datetime类型
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
            else:
                result[key] = value

    return result


class BaseAdminCrudService:
    """管理资源通用服务基类"""

    def __init__(self, session: Session, model: type[Any] | None = None, **kwargs):
        self.session = session
        self.model = model
        self.soft_delete = kwargs.get("soft_delete", False)
        self.relations = kwargs.get("relations", ())
        self.is_tree = kwargs.get("is_tree", False)
        self.parent_field = kwargs.get("parent_field", "parent_id")

    def _apply_query(
        self,
        statement,
        model,
        query: CrudQuery | None,
        current_user: User | None = None,
        fallback_field: str = "created_at",
        relations: tuple[RelationConfig, ...] = (),
    ):
        """统一应用所有查询规则 (过滤、关键字、范围、排序、数据权限)"""
        from app.framework.router.query_builder import QueryBuilder

        builder = QueryBuilder(model, query)

        # 获取当前用户ID和数据权限上下文，用于 QueryBuilder 自动注入隔离条件
        current_user_id = current_user.id if current_user else None
        data_scope = resolve_data_scope(self.session, current_user) if current_user else None

        # 链式应用所有规则 (包括软删除、数据权限过滤和关系 Join)
        return builder.apply_all(statement, data_scope=data_scope, current_user_id=current_user_id, relations=relations)

    def info(self, id: Any, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> Any:
        """获取资源详情"""
        statement = select(self.model).where(self.model.id == id)
        statement = self._apply_query(statement, self.model, None, current_user, relations=relations)

        result = self.session.exec(statement).first()
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

        # 处理可能的 Tuple 结果 (Model + Relation Columns)
        return self._finalize_data(self._row_to_dict(result))

    def list(
        self,
        query: CrudQuery | None = None,
        current_user: User | None = None,
        relations: tuple[RelationConfig, ...] | None = None,
        is_tree: bool | None = None,
        parent_field: str | None = None,
    ) -> list[dict]:
        """通用获取列表"""
        # 使用传入参数或实例属性（来自元数据注入）
        active_relations = relations if relations is not None else self.relations
        active_is_tree = is_tree if is_tree is not None else self.is_tree
        active_parent_field = parent_field if parent_field is not None else self.parent_field

        statement = select(self.model)
        statement = self._apply_query(statement, self.model, query, current_user, relations=active_relations)
        results = list(self.session.exec(statement).all())
        data = [self._row_to_dict(r) for r in results]

        if active_is_tree:
            return self._finalize_data(self._to_tree(data, parent_field=active_parent_field))
        return self._finalize_data(data)

    def page(
        self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()
    ) -> PageResult[dict]:
        """通用获取分页"""
        page = query.page or 1
        page_size = query.size or 10

        statement = select(self.model)
        statement = self._apply_query(statement, self.model, query, current_user, relations=relations)

        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())

        results = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())

        return PageResult(
            items=self._finalize_data([self._row_to_dict(r) for r in results]),
            total=total,
            page=page,
            page_size=page_size,
        )

    # 声明生命周期钩子签名，子类可按需覆盖 (支持 data/payload 参数)
    def _before_add(self, data: dict) -> dict:
        return data

    def _after_add(self, entity: Any, payload: Any = None) -> None:
        pass

    def _before_update(self, data: dict, entity: Any) -> dict:
        return data

    def _after_update(self, entity: Any, payload: Any = None) -> None:
        pass

    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
        return ids

    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        pass

    def _finalize_data(self, data: Any) -> Any:
        """
        统一出口转换：将数据转换为前端期望的 camelCase 格式。
        支持 dict 和 list[dict]。
        """
        from app.framework.api.naming import resolve_alias

        if data is None:
            return None
        if isinstance(data, list):
            return [self._finalize_data(item) for item in data]
        if isinstance(data, dict):
            return {resolve_alias(k): v for k, v in data.items()}
        return data

    def _row_to_dict(self, row: Any) -> dict:
        """
        将查询结果转换为字典。保持内部使用蛇形命名(snake_case)以支持子类逻辑。
        """
        if row is None:
            return {}

        raw_data = {}
        # 1. 如果直接就是模型实例
        if isinstance(row, self.model):
            raw_data = row.model_dump()
        # 2. 如果是 SQLAlchemy Row
        elif hasattr(row, "_mapping"):
            mapping = dict(row._mapping)
            if isinstance(row[0], self.model):
                raw_data = row[0].model_dump()
                raw_data.update(mapping)
                raw_data.pop(self.model.__name__, None)
            else:
                raw_data = mapping
        # 3. 其他 Row/Tuple 类型
        elif hasattr(row, "_asdict"):
            data_map = row._asdict()
            if isinstance(row[0], self.model):
                raw_data = row[0].model_dump()
                raw_data.update(data_map)
                raw_data.pop(self.model.__name__, None)
            else:
                raw_data = data_map
        elif isinstance(row, tuple):
            if len(row) > 0 and isinstance(row[0], self.model):
                raw_data = row[0].model_dump()
                if hasattr(row, "_fields"):
                    for i, field in enumerate(row._fields):
                        if i == 0:
                            continue
                        raw_data[field] = row[i]
            else:
                raw_data = {"id": row[0]} if len(row) > 0 else {}
        elif isinstance(row, dict):
            raw_data = row
        elif hasattr(self.model, "id") and isinstance(row, (int, str)):
            raw_data = {"id": row}

        return raw_data

    def _add_single_in_tx(self, item: Any) -> Any:
        data = item.model_dump() if hasattr(item, "model_dump") else (item.copy() if isinstance(item, dict) else item)
        data = self._before_add(data)

        entity = self.model(**data)
        self.session.add(entity)
        self.session.flush()

        self._after_add(entity, item)
        return entity

    def add(self, payload: Any) -> Any:
        """通用新增资源 (支持单条或列表)"""
        if isinstance(payload, list):
            with transaction(self.session):
                entities = [self._add_single_in_tx(item) for item in payload]
            for entity in entities:
                self.session.refresh(entity)
            return entities

        with transaction(self.session):
            entity = self._add_single_in_tx(payload)
        self.session.refresh(entity)
        return entity

    def update(self, payload: Any) -> Any:
        """通用更新资源"""
        id_val = payload.get("id") if isinstance(payload, dict) else getattr(payload, "id", None)
        if id_val is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少更新实体的 id")
        entity = self.session.get(self.model, id_val)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

        # 记录变更前的数据
        old_data = entity_to_dict(entity)

        # exclude_unset：仅写入请求中实际提供的字段，支持部分更新（cl-switch 等行内编辑只传 {id, 字段}）。
        # 全量编辑表单提交时所有字段均 set，行为与原先一致；各 _before_update 已用 data.get()/"k" in data 安全访问。
        data = (
            payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump")
            else (payload.copy() if isinstance(payload, dict) else payload)
        )

        with transaction(self.session):
            data = self._before_update(data, entity)

            for key, value in data.items():
                if key == "id":
                    continue
                setattr(entity, key, value)

            self.session.add(entity)
            self.session.flush()

            # 记录变更后的数据
            new_data = entity_to_dict(entity)
            diff = compute_entity_diff(old_data, new_data)

            # 如果有变更，记录到操作日志（在同一事务内持久化）
            if diff:
                self._log_entity_change(entity.id, "update", diff, payload)

            self._after_update(entity, payload)

        self.session.refresh(entity)
        return entity

    def delete(self, ids: list[int], payload: Any = None, soft_delete: bool | None = None) -> dict:
        """通用删除资源"""
        if not ids:
            return {"success": True, "deleted_ids": []}

        active_soft_delete = soft_delete if soft_delete is not None else self.soft_delete
        target_ids: set[int] = set()

        with transaction(self.session):
            filtered_ids = self._before_delete(ids, payload)
            target_ids = set(filtered_ids)

            # 记录删除前的数据
            entities_before_delete = {}
            if active_soft_delete:
                # 软删除：收集所有受影响实体的数据
                all_ids = self._collect_descendant_ids(filtered_ids)
                target_ids.update(all_ids)

                for entity in self.session.exec(select(self.model).where(self.model.id.in_(list(target_ids)))).all():
                    entities_before_delete[entity.id] = entity_to_dict(entity)

                from sqlalchemy import update

                statement = (
                    update(self.model)
                    .where(self.model.id.in_(list(target_ids)))
                    .where(self.model.delete_time.is_(None))  # 避免重复软删除
                    .values(delete_time=datetime.now(UTC))
                )
                self.session.execute(statement)
            else:
                # 物理删除逻辑
                entities = list(self.session.exec(select(self.model).where(self.model.id.in_(filtered_ids))).all())
                for entity in entities:
                    entities_before_delete[entity.id] = entity_to_dict(entity)
                    self.session.delete(entity)

            self.session.flush()

            # 记录删除操作到日志（纳入同一事务）
            for entity_id, entity_data in entities_before_delete.items():
                self._log_entity_change(entity_id, "delete", {"deleted_data": entity_data}, payload)

            # 补齐触发后置删除钩子
            self._after_delete(list(target_ids), payload)

        return {"success": True, "deleted_ids": sorted(list(target_ids))}

    def _to_tree(self, data: list[dict], parent_field: str = "parent_id", id_field: str = "id") -> list[dict]:
        """将扁平列表转换为树形结构"""
        item_dict = {item[id_field]: {**item, "children": []} for item in data}
        tree = []
        for item in item_dict.values():
            parent_id = item.get(parent_field)
            if parent_id and parent_id in item_dict:
                item_dict[parent_id]["children"].append(item)
            else:
                tree.append(item)
        return tree

    def _collect_descendant_ids(self, root_ids: list[int]) -> list[int]:
        """递归收集所有后代 ID"""
        if not hasattr(self.model, "parent_id"):
            return []

        # 简单实现：一次性查出所有数据在内存中构建（适用于字典、菜单等小规模树）
        # 对于超大规模树，应改用递归 SQL 或闭包表
        all_rows = list(self.session.exec(select(self.model.id, self.model.parent_id)).all())
        children_map = {}
        for row in all_rows:
            children_map.setdefault(row.parent_id, []).append(row.id)

        result = set()
        stack = list(root_ids)
        while stack:
            curr = stack.pop()
            if curr in result:
                continue
            result.add(curr)
            if curr in children_map:
                stack.extend(children_map[curr])

        return list(result)

    def _log_entity_change(self, entity_id: int, operation: str, diff: dict, payload: Any = None) -> None:
        """
        记录实体变更到操作日志

        Args:
            entity_id: 实体ID
            operation: 操作类型 (update/delete)
            diff: 变更差异或删除的数据
            payload: 请求载荷（用于获取上下文信息）
        """
        try:
            import json

            from app.modules.base.model.sys import SysLog

            # 获取当前用户信息（如果有）
            current_user_id = None
            if payload:
                user_obj = get_payload_attr(payload, "_current_user") or get_payload_attr(payload, "current_user")
                if user_obj:
                    current_user_id = (
                        getattr(user_obj, "id", None)
                        if hasattr(user_obj, "id")
                        else (user_obj.get("id") if isinstance(user_obj, dict) else None)
                    )

            # 构建日志消息
            model_name = self.model.__name__ if hasattr(self.model, "__name__") else "Entity"
            if operation == "update":
                message = f"更新 {model_name} #{entity_id}"
                params_json = json.dumps({"diff": diff}, ensure_ascii=False, default=str)
            else:  # delete
                message = f"删除 {model_name} #{entity_id}"
                params_json = json.dumps({"deleted_data": diff}, ensure_ascii=False, default=str)

            log = SysLog(
                user_id=current_user_id,
                action=f"/admin/{model_name.lower()}/{operation}",
                method="POST" if operation == "update" else "DELETE",
                params=params_json,
                ip=None,  # 中间件中会设置
                status=1,
                message=message,
            )
            self.session.add(log)
            # 不commit，让外层事务处理
        except Exception as exc:
            # 日志记录失败不影响主流程
            logger.warning(f"记录实体变更日志失败 - model: {model_name}, id: {entity_id}", exc_info=exc)
