"""
Base 模块管理服务
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import load_only
from sqlmodel import Session, select

from app.core.security import hash_password, add_user_all_tokens_to_blacklist
from app.framework.controller_meta import CrudQuery, RelationConfig
from app.modules.base.compat import get_menu_parent_code, get_resource_compat
from app.modules.base.model.auth import (
    Department,
    DepartmentCreateRequest,
    DepartmentDeleteRequest,
    DepartmentOrderItem,
    DepartmentRead,
    DepartmentUpdateRequest,
    Menu,
    MenuCreateRequest,
    MenuCreateAutoItem,
    MenuCreateAutoRequest,
    MenuExportRequest,
    MenuImportNode,
    MenuImportRequest,
    MenuParseRequest,
    MenuParseItem,
    MenuRead,
    MenuTreeItem,
    MenuUpdateRequest,
    PageResult,
    Role,
    RoleCreateRequest,
    RoleMenuAssignRequest,
    RoleMenuLink,
    RoleRead,
    RoleUpdateRequest,
    User,
    UserCreateRequest,
    UserInfoItem,
    UserListItem,
    UserMoveRequest,
    UserRoleAssignRequest,
    UserRoleLink,
    UserUpdateRequest,
    RoleDepartmentLink,
)
from app.modules.base.service.authority_service import (
    clear_login_caches,
    clear_login_caches_for_menus,
    clear_login_caches_for_roles,
    clear_login_caches_for_users,
    get_user_permissions,
    get_user_roles,
)
from app.modules.base.service.data_scope_service import can_access_user, resolve_data_scope
from app.core.security import validate_password_strength


from typing import Any, Type
import logging
import json


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
            if hasattr(old_value, 'isoformat'):
                old_value = old_value.isoformat()
            if hasattr(new_value, 'isoformat'):
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
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()
            else:
                result[key] = value

    return result


class BaseAdminCrudService:
    """管理资源通用服务基类"""

    def __init__(self, session: Session, model: Type[Any] | None = None, **kwargs):
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

        # 获取当前用户ID用于数据权限过滤
        current_user_id = current_user.id if current_user else None

        # 链式应用所有规则 (包括软删除过滤和关系 Join)
        return builder.apply_all(statement, data_scope=None, current_user_id=current_user_id, relations=relations)

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
        parent_field: str | None = None
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

    def page(self, query: CrudQuery, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> PageResult[dict]:
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
    def _before_add(self, data: dict) -> dict: return data
    def _after_add(self, entity: Any, payload: Any = None) -> None: pass
    def _before_update(self, data: dict, entity: Any) -> dict: return data
    def _after_update(self, entity: Any, payload: Any = None) -> None: pass
    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]: return ids
    def _after_delete(self, ids: list[int], payload: Any = None) -> None: pass

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
                        if i == 0: continue
                        raw_data[field] = row[i]
            else:
                raw_data = {"id": row[0]} if len(row) > 0 else {}
        elif isinstance(row, dict):
            raw_data = row
        elif hasattr(self.model, "id") and isinstance(row, (int, str)):
            raw_data = {"id": row}

        return raw_data

    def add(self, payload: Any) -> Any:
        """通用新增资源 (支持单条或列表)"""
        if isinstance(payload, list):
            return [self.add(item) for item in payload]
            
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload
        data = self._before_add(data)
        
        entity = self.model(**data)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        
        self._after_add(entity, payload)
        return entity

    def update(self, payload: Any) -> Any:
        """通用更新资源"""
        id_val = getattr(payload, "id", None)
        entity = self.session.get(self.model, id_val)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

        # 记录变更前的数据
        old_data = entity_to_dict(entity)

        data = payload.model_dump() if hasattr(payload, "model_dump") else payload
        data = self._before_update(data, entity)

        for key, value in data.items():
            if key == "id": continue
            setattr(entity, key, value)

        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)

        # 记录变更后的数据
        new_data = entity_to_dict(entity)
        diff = compute_entity_diff(old_data, new_data)

        # 如果有变更，记录到操作日志
        if diff:
            self._log_entity_change(entity.id, "update", diff, payload)

        self._after_update(entity, payload)
        return entity

    def delete(self, ids: list[int], payload: Any = None, soft_delete: bool | None = None) -> dict:
        """通用删除资源"""
        if not ids:
            return {"success": True, "deleted_ids": []}

        ids = self._before_delete(ids, payload)

        # 使用传入参数或实例属性（来自元数据注入）
        active_soft_delete = soft_delete if soft_delete is not None else self.soft_delete

        target_ids = set(ids)

        # 记录删除前的数据
        entities_before_delete = {}
        if active_soft_delete:
            # 软删除：收集所有受影响实体的数据
            all_ids = self._collect_descendant_ids(ids)
            target_ids.update(all_ids)

            for entity in self.session.exec(select(self.model).where(self.model.id.in_(list(target_ids)))).all():
                entities_before_delete[entity.id] = entity_to_dict(entity)

            from sqlalchemy import update
            statement = (
                update(self.model)
                .where(self.model.id.in_(list(target_ids)))
                .where(self.model.delete_time == None) # 避免重复软删除
                .values(delete_time=datetime.utcnow())
            )
            self.session.execute(statement)
        else:
            # 物理删除逻辑
            entities = list(self.session.exec(select(self.model).where(self.model.id.in_(ids))).all())
            for entity in entities:
                entities_before_delete[entity.id] = entity_to_dict(entity)
                self.session.delete(entity)

        self.session.commit()

        # 记录删除操作到日志
        for entity_id, entity_data in entities_before_delete.items():
            self._log_entity_change(entity_id, "delete", {"deleted_data": entity_data}, payload)

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
            if curr in result: continue
            result.add(curr)
            if curr in children_map:
                stack.extend(children_map[curr])
        
        return list(result)

    # 生命周期钩子 (Lifecycle Hooks)
    def _before_add(self, data: dict) -> dict: return data
    def _after_add(self, entity: Any) -> None: pass
    def _before_update(self, data: dict, entity: Any) -> dict: return data
    def _after_update(self, entity: Any) -> None: pass
    def _before_delete(self, ids: list[int]) -> None: pass

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
            from app.modules.base.model.sys import SysLog
            import json

            # 获取当前用户信息（如果有）
            current_user_id = None
            if payload and hasattr(payload, "_current_user"):
                current_user_id = getattr(payload._current_user, "id", None)
            elif payload and hasattr(payload, "current_user"):
                current_user_id = getattr(payload.current_user, "id", None)

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
                message=message
            )
            self.session.add(log)
            # 不commit，让外层事务处理
        except Exception as exc:
            # 日志记录失败不影响主流程
            logger.warning(f"记录实体变更日志失败 - model: {model_name}, id: {entity_id}", exc_info=exc)


class UserAdminService(BaseAdminCrudService):
    """用户资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, User)

    def _after_add(self, entity: User, payload: Any) -> None:
        """用户创建后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            # 获取当前操作者信息
            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 记录安全审计日志
            SysSecurityLogService(self.session).create_entry(
                operator_id=operator_id or 0,
                operator_name=operator_name,
                operator_ip=operator_ip,
                target_type="user",
                target_id=entity.id,
                target_name=entity.username,
                operation="create",
                module="user",
                resource_path=f"/admin/base/sys/user/{entity.id}",
                new_value=json.dumps({"username": entity.username, "full_name": entity.full_name, "email": entity.email}, ensure_ascii=False),
                business_type="user_management",
                status=1,
                remark="创建新用户"
            )
        except Exception as exc:
            logger.warning(f"记录用户创建审计日志失败 - user_id: {entity.id}", exc_info=exc)

        if hasattr(payload, "role_ids"):
            self._replace_user_roles(entity.id, payload.role_ids)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None, relations: tuple[RelationConfig, ...] = ()) -> list[UserListItem]:
        items = super().list(query, current_user, relations)
        return [UserListItem.model_validate(item) for item in items]

    def _row_to_dict(self, row: Any) -> dict:
        # 获取基础数据字典
        data = super()._row_to_dict(row)
        if not data:
            return {}
        # 处理 nick_name 默认值 (如果 DB 中为 NULL)
        if data.get("nick_name") is None:
            data["nick_name"] = data.get("full_name") or data.get("name") or data.get("username") or ""

        # 获取用户 ID 用于查询角色
        user_id = data.get("id")
        if user_id:
            roles = get_user_roles(self.session, user_id)
            data["role_ids"] = [role.id for role in roles if role.id is not None]
            data["role_name"] = ",".join(role.name for role in roles if role.name)
        else:
            data["role_ids"] = []
            data["role_name"] = ""
            
        return data

    # 钩子实现 (Hooks)
    def _before_add(self, data: dict) -> dict:
        username = data.get("username")
        existing = self.session.exec(select(User).where(User.username == username)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

        password = data.pop("password", None)
        if password:
            # 验证密码强度
            validate_password_strength(password)
            data["password_hash"] = hash_password(password)
        data["nick_name"] = data.get("nick_name", "") or data.get("full_name", "")
        data.pop("role_ids", None)
        return data

    def _after_add(self, entity: User, payload: Any) -> None:
        if hasattr(payload, "role_ids"):
            self._replace_user_roles(entity.id, payload.role_ids)

    def _before_update(self, data: dict, entity: User) -> dict:
        if data.get("password"):
            # 验证密码强度
            validate_password_strength(data["password"])
            data["password_hash"] = hash_password(data.pop("password"))
            entity.password_version += 1
            entity.password_changed_at = datetime.utcnow()  # 记录密码修改时间
        else:
            data.pop("password", None)
        data["nick_name"] = data.get("nick_name", "") or data.get("full_name", entity.full_name)
        data.pop("role_ids", None)
        return data

    def _after_update(self, entity: User, payload: Any) -> None:
        """用户更新后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            # 获取当前操作者信息
            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 检查是否有敏感操作需要记录
            sensitive_operations = []
            diff_data = {}

            # 检查是否禁用/启用用户
            if hasattr(payload, "is_active"):
                if not payload.is_active:
                    sensitive_operations.append("disable_user")
                    diff_data["is_active"] = {"old": "enabled", "new": "disabled"}
                else:
                    sensitive_operations.append("enable_user")
                    diff_data["is_active"] = {"old": "disabled", "new": "enabled"}

            # 检查是否重置密码
            if hasattr(payload, "password") and payload.password:
                sensitive_operations.append("reset_password")
                diff_data["password"] = {"old": "******", "new": "******"}

            # 如果有敏感操作，记录审计日志
            if sensitive_operations:
                for op in sensitive_operations:
                    SysSecurityLogService(self.session).create_entry(
                        operator_id=operator_id or 0,
                        operator_name=operator_name,
                        operator_ip=operator_ip,
                        target_type="user",
                        target_id=entity.id,
                        target_name=entity.username,
                        operation=op,
                        module="user",
                        resource_path=f"/admin/base/sys/user/{entity.id}",
                        diff_data=json.dumps(diff_data, ensure_ascii=False),
                        business_type="user_management",
                        status=1,
                        remark=f"执行敏感操作: {', '.join(sensitive_operations)}"
                    )
        except Exception as exc:
            logger.warning(f"记录用户更新审计日志失败 - user_id: {entity.id}", exc_info=exc)

        if hasattr(payload, "role_ids"):
            self._replace_user_roles(entity.id, payload.role_ids)

        # 如果用户被禁用，将该用户的所有Token加入黑名单
        # 检查payload中的is_active字段，如果为False则禁用用户
        if hasattr(payload, "is_active") and not payload.is_active:
            add_user_all_tokens_to_blacklist(entity.id)
        else:
            clear_login_caches(entity.id)

    def _before_delete(self, ids: list[int]) -> list[int]:
        users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())
        protected_users = [user.username for user in users if user.is_super_admin]
        if protected_users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不能删除超级管理员: {', '.join(protected_users)}")
        return ids

    def _after_delete(self, ids: list[int]) -> None:
        """用户删除后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            # 获取被删除的用户信息（在删除前获取）
            users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())

            for user in users:
                # 获取当前操作者信息
                operator_id = getattr(self, "_operator_id", None) or 0
                operator_name = getattr(self, "_operator_name", None) or "system"

                # 记录删除审计日志
                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id,
                    operator_name=operator_name,
                    operator_ip=None,
                    target_type="user",
                    target_id=user.id,
                    target_name=user.username,
                    operation="delete",
                    module="user",
                    resource_path=f"/admin/base/sys/user/{user.id}",
                    old_value=json.dumps({"username": user.username, "full_name": user.full_name, "email": user.email}, ensure_ascii=False),
                    business_type="user_management",
                    status=1,
                    remark="删除用户"
                )
        except Exception as exc:
            logger.warning(f"记录用户删除审计日志失败 - user_ids: {ids}", exc_info=exc)

        # 将被删除用户的所有Token加入黑名单
        for user_id in ids:
            add_user_all_tokens_to_blacklist(user_id)
        clear_login_caches_for_users(ids)


    def _replace_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        existing_links = list(self.session.exec(select(UserRoleLink).where(UserRoleLink.user_id == user_id)).all())
        for link in existing_links:
            self.session.delete(link)
        if role_ids:
            roles = list(self.session.exec(select(Role).where(Role.id.in_(role_ids))).all())
            found_role_ids = {role.id for role in roles if role.id is not None}
            missing_ids = sorted(set(role_ids) - found_role_ids)
            if missing_ids:
                self.session.rollback()
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {missing_ids}")
            for role_id in role_ids:
                self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))
        self.session.commit()

    def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
        user = self.session.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        self._replace_user_roles(payload.user_id, payload.role_ids)
        clear_login_caches(payload.user_id)
        self.session.refresh(user)
        return UserListItem.model_validate(self._row_to_dict(user))

    def move(self, payload: dict | UserMoveRequest) -> dict:
        if isinstance(payload, dict):
            payload = UserMoveRequest(**payload)
        department = self.session.get(Department, payload.department_id)
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        users = list(self.session.exec(select(User).where(User.id.in_(payload.user_ids))).all())
        for user in users:
            user.department_id = payload.department_id
            self.session.add(user)
        self.session.commit()
        for user in users:
            clear_login_caches(user.id)
        return {"success": True}


class RoleAdminService(BaseAdminCrudService):
    """角色资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Role)

    def _after_add(self, entity: Role, payload: Any) -> None:
        """角色创建后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            SysSecurityLogService(self.session).create_entry(
                operator_id=operator_id or 0,
                operator_name=operator_name,
                operator_ip=operator_ip,
                target_type="role",
                target_id=entity.id,
                target_name=entity.name,
                operation="create",
                module="role",
                resource_path=f"/admin/base/sys/role/{entity.id}",
                new_value=json.dumps({"name": entity.name, "code": entity.code, "data_scope": entity.data_scope}, ensure_ascii=False),
                business_type="role_management",
                status=1,
                remark="创建新角色"
            )
        except Exception as exc:
            logger.warning(f"记录角色创建审计日志失败 - role_id: {entity.id}", exc_info=exc)

        if hasattr(payload, "menu_ids"):
            self._replace_role_menus(entity.id, payload.menu_ids)
        if hasattr(payload, "department_ids"):
            self._replace_role_departments(entity.id, payload.department_ids)

    def _after_update(self, entity: Role, payload: Any) -> None:
        """角色更新后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            operator_id = getattr(payload, "_operator_id", None) or getattr(payload, "current_user_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = get_request_ip_from_payload(payload)

            # 检查权限调整操作
            sensitive_operations = []
            if hasattr(payload, "menu_ids"):
                sensitive_operations.append("update_permissions")
            if hasattr(payload, "department_ids"):
                sensitive_operations.append("update_data_scope")
            if hasattr(payload, "data_scope"):
                sensitive_operations.append("update_data_scope")

            if sensitive_operations:
                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id or 0,
                    operator_name=operator_name,
                    operator_ip=operator_ip,
                    target_type="role",
                    target_id=entity.id,
                    target_name=entity.name,
                    operation="update",
                    module="role",
                    resource_path=f"/admin/base/sys/role/{entity.id}",
                    business_type="role_management",
                    status=1,
                    remark=f"调整角色权限: {', '.join(sensitive_operations)}"
                )
        except Exception as exc:
            logger.warning(f"记录角色更新审计日志失败 - role_id: {entity.id}", exc_info=exc)

        if hasattr(payload, "menu_ids"):
            self._replace_role_menus(entity.id, payload.menu_ids)
        if hasattr(payload, "department_ids"):
            self._replace_role_departments(entity.id, payload.department_ids)
        clear_login_caches_for_roles(self.session, [entity.id])

    def _after_delete(self, ids: list[int]) -> None:
        """角色删除后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService

            roles = list(self.session.exec(select(Role).where(Role.id.in_(ids))).all())

            for role in roles:
                operator_id = getattr(self, "_operator_id", None) or 0
                operator_name = getattr(self, "_operator_name", None) or "system"

                SysSecurityLogService(self.session).create_entry(
                    operator_id=operator_id,
                    operator_name=operator_name,
                    operator_ip=None,
                    target_type="role",
                    target_id=role.id,
                    target_name=role.name,
                    operation="delete",
                    module="role",
                    resource_path=f"/admin/base/sys/role/{role.id}",
                    old_value=json.dumps({"name": role.name, "code": role.code}, ensure_ascii=False),
                    business_type="role_management",
                    status=1,
                    remark="删除角色"
                )
        except Exception as exc:
            logger.warning(f"记录角色删除审计日志失败 - role_ids: {ids}", exc_info=exc)

        clear_login_caches_for_roles(self.session, ids)

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)
        # 补充关联列表
        data["menu_ids"] = [link.menu_id for link in self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == row.id)).all()]
        data["department_ids"] = [link.department_id for link in self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == row.id)).all()]
        return data

    def _before_add(self, data: dict) -> dict:
        label = data.get("label")
        code = data.get("code") or label
        existing = self.session.exec(select(Role).where((Role.code == code) | (Role.label == label))).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")
        
        data["code"] = code
        data["data_scope"] = "department" if data.get("department_ids") else "self"
        return data

    def _after_add(self, entity: Role, payload: Any) -> None:
        if hasattr(payload, "menu_ids"):
            self._replace_role_menus(entity.id, payload.menu_ids)
        if hasattr(payload, "department_ids"):
            self._replace_role_departments(entity.id, payload.department_ids)

    def _before_update(self, data: dict, entity: Role) -> dict:
        label = data.get("label") or entity.label
        code = data.get("code") or data.get("label") or entity.code
        
        duplicate = self.session.exec(
            select(Role).where((Role.id != entity.id) & ((Role.code == code) | (Role.label == label)))
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")

        if "department_ids" in data:
            data["data_scope"] = "department" if data["department_ids"] else "self"
        return data

    def _after_update(self, entity: Role, payload: Any) -> None:
        if hasattr(payload, "menu_ids"):
            self._replace_role_menus(entity.id, payload.menu_ids)
        if hasattr(payload, "department_ids"):
            self._replace_role_departments(entity.id, payload.department_ids)
        self._clear_role_related_caches([entity.id])

    def _before_delete(self, ids: list[int]) -> list[int]:
        roles = list(self.session.exec(select(Role).where(Role.id.in_(ids))).all())
        if any(role.code == "admin" for role in roles):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除系统管理员角色")
        
        # 收集受影响的用户 ID 以便后续清理缓存
        affected_user_ids = [link.user_id for link in self.session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(ids))).all()]
        self._affected_user_ids_storage = affected_user_ids  # 临时存储
        return ids

    def _after_delete(self, ids: list[int]) -> None:
        if hasattr(self, "_affected_user_ids_storage"):
            clear_login_caches_for_users(self._affected_user_ids_storage)
            del self._affected_user_ids_storage

    def assign_menus(self, payload: RoleMenuAssignRequest) -> dict:
        role = self.session.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        self._replace_role_menus(payload.role_id, payload.menu_ids)
        self._clear_role_related_caches([payload.role_id])
        return {"success": True, "role_id": payload.role_id, "menu_ids": payload.menu_ids}


    def _replace_role_menus(self, role_id: int, menu_ids: list[int]) -> None:
        for link in list(self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role_id)).all()):
            self.session.delete(link)
        if menu_ids:
            menus = list(self.session.exec(select(Menu).where(Menu.id.in_(menu_ids))).all())
            found_menu_ids = {menu.id for menu in menus if menu.id is not None}
            missing_ids = sorted(set(menu_ids) - found_menu_ids)
            if missing_ids:
                self.session.rollback()
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"菜单不存在: {missing_ids}")
            for menu_id in menu_ids:
                self.session.add(RoleMenuLink(role_id=role_id, menu_id=menu_id))
        self.session.commit()

    def _replace_role_departments(self, role_id: int, department_ids: list[int]) -> None:
        for link in list(self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == role_id)).all()):
            self.session.delete(link)
        if department_ids:
            departments = list(self.session.exec(select(Department).where(Department.id.in_(department_ids))).all())
            found_ids = {item.id for item in departments if item.id is not None}
            missing_ids = sorted(set(department_ids) - found_ids)
            if missing_ids:
                self.session.rollback()
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"部门不存在: {missing_ids}")
            for department_id in department_ids:
                self.session.add(RoleDepartmentLink(role_id=role_id, department_id=department_id))
        self.session.commit()

    def _clear_role_related_caches(self, role_ids: list[int]) -> None:
        clear_login_caches_for_roles(self.session, role_ids)


class DepartmentAdminService(BaseAdminCrudService):
    """部门资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Department)

    def _before_add(self, data: dict) -> dict:
        data["is_active"] = True
        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        return data

    def delete(self, ids: list[int], payload: Any = None, soft_delete: bool | None = None) -> dict:
        if not ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少待删除的部门 ID")
        delete_user = bool(payload.delete_user) if payload else False
        department_ids = self._collect_descendant_department_ids(ids)
        root_ids = set(ids)
        for department_id in sorted(department_ids, reverse=True):
            department = self.session.get(Department, department_id)
            if not department:
                continue
            if not delete_user:
                fallback_department_id = department.parent_id
                if department_id in root_ids and fallback_department_id is not None:
                    for user in list(self.session.exec(select(User).where(User.department_id == department_id)).all()):
                        user.department_id = fallback_department_id
                        self.session.add(user)
            else:
                for user in list(self.session.exec(select(User).where(User.department_id == department_id)).all()):
                    clear_login_caches(user.id)
                    self.session.delete(user)
            for link in list(self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.department_id == department_id)).all()):
                self.session.delete(link)
            self.session.delete(department)
        self.session.commit()
        return {"success": True, "deleted_ids": department_ids}

    def order(self, payload: list[dict] | list[DepartmentOrderItem]) -> dict:
        for item in payload:
            data = item if isinstance(item, DepartmentOrderItem) else DepartmentOrderItem(**item)
            department = self.session.get(Department, data.id)
            if not department:
                continue
            department.parent_id = data.parent_id
            department.sort_order = data.sort_order
            self.session.add(department)
        self.session.commit()
        return {"success": True}

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)

        # 补充 parent_name
        if data.get("parent_id"):
            parent = self.session.get(Department, data["parent_id"])
            if parent:
                data["parent_name"] = parent.name
        return data



class MenuAdminService(BaseAdminCrudService):
    """菜单资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, Menu)

    def _row_to_dict(self, row: Any) -> dict:
        data = super()._row_to_dict(row)
        data["type"] = self._normalize_menu_type_int(data.get("type", "button"))

        # 补充 parent_name
        if data.get("parent_id"):
            parent = self.session.get(Menu, data["parent_id"])
            if parent:
                data["parent_name"] = parent.name
        return data

    def _before_add(self, data: dict) -> dict:
        code = data.get("code") or self._generate_menu_code(data)
        existing = self.session.exec(select(Menu).where(Menu.code == code)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")
        
        data["code"] = code
        data["type"] = self._normalize_menu_type(data.get("type"))
        return data

    def _before_update(self, data: dict, entity: Menu) -> dict:
        if "code" in data:
            code = data["code"]
            duplicate = self.session.exec(select(Menu).where((Menu.id != entity.id) & (Menu.code == code))).first()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")

        if "type" in data: data["type"] = self._normalize_menu_type(data["type"])
        return data

    def _after_add(self, entity: Menu, payload: Any = None) -> None:
        self._clear_menu_related_caches([entity.id])

    def _after_update(self, entity: Menu, payload: Any = None) -> None:
        self._clear_menu_related_caches([entity.id])

    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        self._clear_menu_related_caches(ids)


    def tree(self) -> list[dict]:
        return self.list(is_tree=True)

    def role_menu_ids(self, role_id: int) -> list[int]:
        return [link.menu_id for link in self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role_id)).all()]

    def export(self, payload: MenuExportRequest | dict) -> list[dict]:
        if isinstance(payload, dict):
            payload = MenuExportRequest(**payload)
        menu_ids = self._collect_descendant_menu_ids(payload.ids)
        menus = list(self.session.exec(select(Menu).where(Menu.id.in_(menu_ids)).order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())
        tree = self._build_tree(menus)
        selected_ids = set(payload.ids)
        result = [self._menu_tree_to_import_node(node) for node in tree if node.id in selected_ids]
        return [item.model_dump(mode="json", by_alias=True) for item in result]

    def import_menu(self, payload: MenuImportRequest | dict) -> dict:
        if isinstance(payload, dict):
            payload = MenuImportRequest(**payload)
        for item in payload.menus:
            self._upsert_import_node(item, None)
        self.session.commit()
        self._clear_menu_related_caches(list(self.session.exec(select(Menu.id)).all()))
        return {"success": True}

    def create_auto(self, payload: MenuCreateAutoRequest | dict) -> list[MenuRead]:
        if isinstance(payload, dict):
            payload = MenuCreateAutoRequest(**payload)
        created: list[MenuRead] = []
        for item in payload.items:
            created.append(self._build_menu_read(self._upsert_auto_menu(item)))
        return created

    def parse_menu_candidates(self, payload: MenuParseRequest, eps_catalog: dict[str, list[dict[str, Any]]]) -> dict:
        prefixes = set(payload.prefixes)
        items: list[dict[str, Any]] = []
        for module_name, controllers in eps_catalog.items():
            for controller in controllers:
                prefix = controller.get("prefix") or ""
                if prefixes and prefix not in prefixes and controller.get("name") not in prefixes:
                    continue
                resource = self._infer_resource_from_prefix(prefix)
                if not resource:
                    continue
                items.append(
                    MenuParseItem(
                        module=module_name,
                        resource=resource,
                        prefix=prefix,
                        controller=controller.get("name") or resource.split("/")[-1],
                        name=self._guess_menu_name(controller.get("name") or resource.split("/")[-1]),
                        path=self._build_router_from_resource(module_name, resource),
                        component=self._build_view_path_from_resource(module_name, resource),
                        icon=None,
                        parent_code=get_menu_parent_code(module_name, resource),
                        api=[
                            {
                                "name": api.get("name"),
                                "method": api.get("method"),
                                "path": api.get("path"),
                                "summary": self._guess_action_summary(api.get("name"), api.get("path")),
                                "permission": self._build_permission_from_resource(module_name, resource, api.get("name"), api.get("path")),
                            }
                            for api in controller.get("api", [])
                        ],
                    ).model_dump(mode="json", by_alias=True)
                )
        items.sort(key=lambda entry: (entry["module"], entry["resource"], entry["router"]))
        return {"list": items}

    def _build_menu_read(self, menu: Menu, parent_name: str | None = None) -> MenuRead:
        """构建菜单响应对象"""
        return MenuRead.model_validate(menu).model_copy(update={"parent_name": parent_name})

    @staticmethod
    def _normalize_menu_type_int(value: str | int) -> int:
        if value in (0, "0", "group", "dir"):
            return 0
        if value in (1, "1", "menu"):
            return 1
        return 2

    def current_tree(self, current_user: User) -> list[MenuTreeItem]:
        statement = select(Menu).where(Menu.is_active == True)  # noqa: E712
        if not current_user.is_super_admin:
            from app.modules.base.service.authority_service import get_user_roles
            role_ids = [role.id for role in get_user_roles(self.session, current_user.id) if role.id is not None]
            if not role_ids:
                return []
            statement = (
                select(Menu)
                .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
                .where(RoleMenuLink.role_id.in_(role_ids), Menu.is_active == True)  # noqa: E712
            )
        menus = list(self.session.exec(statement.order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())
        navigation_menus = [menu for menu in menus if menu.type in {"menu", "group"} or menu.path]
        expanded: dict[int, Menu] = {menu.id: menu for menu in navigation_menus}
        for menu in navigation_menus:
            parent_id = menu.parent_id
            while parent_id is not None:
                parent = self.session.get(Menu, parent_id)
                if not parent or not parent.is_active:
                    break
                expanded[parent.id] = parent
                parent_id = parent.parent_id
        
        # 预加载所有涉及到的节点的父级名称
        name_map = {m.id: m.name for m in expanded.values()}
        menu_list = sorted(expanded.values(), key=lambda item: (item.sort_order, item.created_at))
        
        # 构建树时，我们需要一个能够传递 parent_name 的 build_tree
        return self._build_tree_with_names(menu_list, name_map)

    def _build_tree_with_names(self, menus: list[Menu], name_map: dict[int, str]) -> list[MenuTreeItem]:
        nodes = {
            menu.id: MenuTreeItem(**self._build_menu_read(menu, parent_name=name_map.get(menu.parent_id)).model_dump(by_alias=True))
            for menu in menus
        }
        children_map: dict[int | None, list[MenuTreeItem]] = defaultdict(list)
        for menu in menus:
            children_map[menu.parent_id].append(nodes[menu.id])
        for parent_id, children in children_map.items():
            children.sort(key=lambda item: (item.sort_order, item.created_at))
            if parent_id in nodes:
                nodes[parent_id].children = children
        return children_map.get(None, [])

    def current_list(self, current_user: User) -> list[MenuRead]:
        """获取当前用户授权的扁平菜单列表"""
        statement = select(Menu).where(Menu.is_active == True)  # noqa: E712
        if not current_user.is_super_admin:
            from app.modules.base.service.authority_service import get_user_roles
            role_ids = [role.id for role in get_user_roles(self.session, current_user.id) if role.id is not None]
            if not role_ids:
                return []
            statement = (
                select(Menu)
                .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
                .where(RoleMenuLink.role_id.in_(role_ids), Menu.is_active == True)  # noqa: E712
            )
        menus = list(self.session.exec(statement.order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())
        
        # 预加载父级名称以提高性能
        menu_map = {menu.id: menu for menu in menus}
        # 如果是超管，可能需要所有菜单的名称，如果不是，只需在授权范围内的
        # 为了保险起见，如果有 parent_id 不在 menu_map 中，我们再查一下数据库
        all_parent_ids = {menu.parent_id for menu in menus if menu.parent_id is not None}
        missing_parent_ids = all_parent_ids - set(menu_map.keys())
        if missing_parent_ids:
            extra_parents = list(self.session.exec(select(Menu).where(Menu.id.in_(list(missing_parent_ids)))).all())
            for p in extra_parents:
                menu_map[p.id] = p
        
        return [self._build_menu_read(menu, parent_name=menu_map[menu.parent_id].name if menu.parent_id in menu_map else None) for menu in menus]



    @staticmethod
    def _normalize_menu_type(value: int | str) -> str:
        if value in (0, "0", "group", "dir"):
            return "group"
        if value in (1, "1", "menu"):
            return "menu"
        return "button"

    def _generate_menu_code(self, payload: MenuCreateRequest | MenuUpdateRequest) -> str:
        seed = payload.code or payload.path or payload.permission or payload.name
        return self._next_unique_code(self._slugify(seed))

    def _generate_import_code(self, node: MenuImportNode) -> str:
        seed = node.path or node.permission or node.name
        return self._next_unique_code(self._slugify(seed))

    @staticmethod
    def _build_view_path(item: MenuCreateAutoItem) -> str | None:
        if item.component:
            return item.component
        if item.module and item.path:
            suffix = item.path.replace(f"/{item.module}", "")
            return f"modules/{item.module}/views{suffix}.vue"
        return None

    @staticmethod
    def _build_auto_permission(item: MenuCreateAutoItem, path: str) -> str:
        prefix = (item.prefix or "").replace("/admin/", "")
        return f"{prefix}{path}".replace("/", ":").strip(":")

    def _upsert_auto_menu(self, item: MenuCreateAutoItem) -> Menu:
        menu = self.session.exec(select(Menu).where(Menu.path == item.path, Menu.type == "menu")).first()
        if menu is None:
            menu = Menu(code=self._next_unique_code(self._slugify(item.path or item.name)), name=item.name)

        menu.parent_id = item.parent_id
        menu.name = item.name
        menu.type = "menu"
        menu.path = item.path
        menu.component = item.component or self._build_view_path(item)
        menu.icon = item.icon
        menu.keep_alive = item.keep_alive
        menu.is_show = True
        menu.sort_order = item.sort_order
        menu.is_active = True
        menu.updated_at = datetime.utcnow()
        self.session.add(menu)
        self.session.commit()
        self.session.refresh(menu)

        for index, api in enumerate(item.api, start=1):
            perms = api.get("permission") or self._build_auto_permission(item, api.get("path") or "")
            if not perms:
                continue
            button = self.session.exec(select(Menu).where(Menu.permission == perms)).first()
            if button is None:
                button = Menu(code=self._next_unique_code(self._slugify(perms)), name=api.get("summary") or api.get("name") or "权限")
            button.parent_id = menu.id
            button.name = api.get("summary") or api.get("name") or "权限"
            button.type = "button"
            button.path = None
            button.component = None
            button.icon = None
            button.keep_alive = False
            button.is_show = True
            button.permission = perms
            button.sort_order = index
            button.is_active = True
            button.updated_at = datetime.utcnow()
            self.session.add(button)
        self.session.commit()
        self._clear_menu_related_caches([menu.id])
        return menu

    def _next_unique_code(self, base: str) -> str:
        candidate = base or "menu"
        index = 1
        while True:
            existing = self.session.exec(select(Menu).where(Menu.code == candidate)).first()
            if existing is None:
                return candidate
            index += 1
            candidate = f"{base}_{index}"

    @staticmethod
    def _slugify(value: str | None) -> str:
        raw = (value or "menu").strip().lower().replace(":", "_").replace("/", "_").replace("-", "_")
        normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized.strip("_") or "menu"

    @staticmethod
    def _infer_resource_from_prefix(prefix: str) -> str | None:
        normalized = prefix.rstrip("/")
        if not normalized.startswith("/admin/"):
            return None
        parts = normalized.removeprefix("/admin/").split("/")
        if len(parts) < 2:
            return None
        return "/".join(parts[1:])

    @staticmethod
    def _guess_menu_name(name: str) -> str:
        mapping = {
            "user": "用户管理",
            "role": "角色管理",
            "menu": "菜单管理",
            "department": "部门管理",
            "param": "参数配置",
            "log": "请求日志",
            "login_log": "登录日志",
            "type": "字典管理",
            "info": "任务列表",
        }
        return mapping.get(name, name)

    @staticmethod
    def _guess_action_summary(name: str | None, path: str | None) -> str:
        action = name or (path or "").rstrip("/").split("/")[-1]
        mapping = {
            "list": "列表查询",
            "page": "分页查询",
            "info": "详情",
            "add": "新增",
            "update": "修改",
            "delete": "删除",
            "assignRoles": "分配角色",
            "assignMenus": "分配菜单",
            "roleMenuIds": "角色菜单",
            "tree": "菜单树",
            "currentTree": "当前菜单树",
            "export": "导出",
            "import": "导入",
            "parse": "解析菜单",
            "create": "创建菜单",
            "order": "排序",
            "cancel": "取消任务",
            "stats": "任务统计",
            "move": "移动部门",
        }
        return mapping.get(action, action or "权限")

    @staticmethod
    def _build_router_from_resource(module: str, resource: str) -> str:
        compat = get_resource_compat(module, resource)
        if compat and compat.compat_module == "task":
            return "/task/list"
        return f"/{module}/{resource}".replace("//", "/")

    @staticmethod
    def _build_view_path_from_resource(module: str, resource: str) -> str | None:
        compat = get_resource_compat(module, resource)
        if compat and compat.compat_module == "task":
            return "modules/task/views/list.vue"
        if module == "base" and resource == "sys/user":
            return "modules/base/views/user/index.vue"
        if module == "base":
            return f"modules/base/views/{resource.split('/')[-1]}.vue"
        if module == "dict":
            return "modules/dict/views/list.vue"
        return f"modules/{module}/views/{resource.split('/')[-1]}.vue"

    @staticmethod
    def _build_permission_from_resource(module: str, resource: str, name: str | None, path: str | None) -> str | None:
        action = name or (path or "").rstrip("/").split("/")[-1]
        if not action:
            return None
        return f"{module}:{resource.replace('/', ':')}:{action}"
