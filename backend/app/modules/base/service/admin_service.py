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

from app.core.security import hash_password
from app.framework.controller_meta import CrudQuery
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


from typing import Any, Type


class BaseAdminCrudService:
    """管理资源通用服务基类"""

    def __init__(self, session: Session, model: Type[Any] | None = None):
        self.session = session
        self.model = model

    def _apply_query(
        self,
        statement,
        model,
        query: CrudQuery | None,
        current_user: User | None = None,
        fallback_field: str = "created_at",
    ):
        """统一应用所有查询规则 (过滤、关键字、范围、排序、数据权限)"""
        from app.framework.router.query_builder import QueryBuilder
        builder = QueryBuilder(model, query)
        
        # 处理数据权限
        data_scope = resolve_data_scope(self.session, current_user) if current_user else None
        current_user_id = current_user.id if current_user else None
        
        # 链式应用
        statement = builder.apply_data_scope(statement, data_scope, current_user_id)
        statement = builder.apply_filters(statement)
        statement = builder.apply_keyword(statement)
        statement = builder.apply_ranges(statement)
        statement = builder.apply_sort(statement, fallback_field=fallback_field)
        
        return statement

    def info(self, id: Any, current_user: User | None = None) -> Any:
        """获取资源详情"""
        entity = self.session.get(self.model, id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
        return entity

    def add(self, payload: Any) -> Any:
        """通用新增资源"""
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload
        data = self._before_add(data)
        
        entity = self.model(**data)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        
        self._after_add(entity)
        return entity

    def update(self, payload: Any) -> Any:
        """通用更新资源"""
        id_val = getattr(payload, "id", None)
        entity = self.session.get(self.model, id_val)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
        
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload
        data = self._before_update(data, entity)
        
        for key, value in data.items():
            if key == "id": continue
            setattr(entity, key, value)
            
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        
        self._after_update(entity)
        return entity

    def delete(self, ids: list[int]) -> dict:
        """通用删除资源"""
        if not ids:
            return {"success": True, "deleted_ids": []}
            
        self._before_delete(ids)
        
        entities = list(self.session.exec(select(self.model).where(self.model.id.in_(ids))).all())
        for entity in entities:
            self.session.delete(entity)
            
        self.session.commit()
        return {"success": True, "deleted_ids": ids}

    # 生命周期钩子 (Lifecycle Hooks)
    def _before_add(self, data: dict) -> dict: return data
    def _after_add(self, entity: Any) -> None: pass
    def _before_update(self, data: dict, entity: Any) -> dict: return data
    def _after_update(self, entity: Any) -> None: pass
    def _before_delete(self, ids: list[int]) -> None: pass


class UserAdminService(BaseAdminCrudService):
    """用户资源管理服务"""

    def __init__(self, session: Session):
        super().__init__(session, User)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[UserListItem]:
        statement = select(User)
        statement = self._apply_query(statement, User, query, current_user, fallback_field="created_at")
        users = list(self.session.exec(statement).all())
        return [self._build_user_list_item(user) for user in users]

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[UserListItem]:
        page = query.page or 1
        page_size = query.size or 10
        
        statement = select(User)
        statement = self._apply_query(statement, User, query, current_user, fallback_field="created_at")
        
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        users = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        
        return PageResult(
            items=[self._build_user_list_item(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
        )

    # 钩子实现 (Hooks)
    def _before_add(self, data: dict) -> dict:
        username = data.get("username")
        existing = self.session.exec(select(User).where(User.username == username)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

        password = data.pop("password", None)
        if password:
            data["password_hash"] = hash_password(password)
        data["full_name"] = data.pop("name")
        data["nick_name"] = data.pop("nickName", None) or data["full_name"]
        data["head_img"] = data.pop("headImg", None)
        data["department_id"] = data.pop("departmentId", None)
        data["is_active"] = int(data.pop("status", 1)) == 1
        data.pop("roleIdList", None)
        data.setdefault("updated_at", datetime.utcnow())
        return data

    def _after_add(self, entity: User) -> None:
        # 获取原始 payload 中的 role_ids (这里需要特殊处理，因为 payload 可能不在钩子参数里)
        # 或者约定 payload 总是包含在某种上下文中。
        # 简单起见，如果是在 UserAdminService 内部，我们可以通过某种方式获取
        pass

    def _before_update(self, data: dict, entity: User) -> dict:
        if data.get("password"):
            data["password_hash"] = hash_password(data.pop("password"))
            entity.password_version += 1
        else:
            data.pop("password", None)
        data["full_name"] = data.pop("name")
        data["nick_name"] = data.pop("nickName", None) or data["full_name"]
        data["head_img"] = data.pop("headImg", None)
        data["department_id"] = data.pop("departmentId", None)
        data["is_active"] = int(data.pop("status", 1)) == 1
        data.pop("roleIdList", None)
        data["updated_at"] = datetime.utcnow()
        return data

    def _after_update(self, entity: User) -> None:
        clear_login_caches(entity.id)

    # 重写 add/update 以处理特定的 Role 逻辑 (或者在基类中完善 payload 透传)
    def add(self, payload: UserCreateRequest) -> UserListItem:
        user = super().add(payload)
        self._replace_user_roles(user.id, payload.roleIdList)
        return self._build_user_list_item(user)

    def update(self, payload: UserUpdateRequest) -> UserListItem:
        user = super().update(payload)
        self._replace_user_roles(user.id, payload.roleIdList)
        return self._build_user_list_item(user)

    def info(self, id: int, current_user: User | None = None) -> UserInfoItem:
        user = super().info(id, current_user=current_user)
        item = self._build_user_list_item(user)
        return UserInfoItem(**item.model_dump(), passwordVersion=user.password_version)

    def delete(self, ids: list[int]) -> dict:
        users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())
        protected_users = [user.username for user in users if user.is_super_admin]
        if protected_users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除超级管理员")
            
        clear_login_caches_for_users(ids)
            
        return super().delete(ids)

    def _build_user_list_item(self, user: User) -> UserListItem:
        roles = get_user_roles(self.session, user.id)
        department = self.session.get(Department, user.department_id) if user.department_id else None
        return UserListItem(
            id=user.id,
            username=user.username,
            name=user.full_name,
            nickName=user.nick_name or user.full_name,
            headImg=user.head_img,
            email=user.email,
            phone=user.phone,
            remark=user.remark,
            departmentId=user.department_id,
            departmentName=department.name if department else None,
            roleIdList=[role.id for role in roles if role.id is not None],
            roleName=",".join(role.name for role in roles),
            status=1 if user.is_active else 0,
            createTime=user.created_at,
            updateTime=user.updated_at or user.created_at,
        )

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
        return self._build_user_list_item(user)

    def move(self, payload: dict | UserMoveRequest) -> dict:
        if isinstance(payload, dict):
            payload = UserMoveRequest(**payload)
        department = self.session.get(Department, payload.departmentId)
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        users = list(self.session.exec(select(User).where(User.id.in_(payload.userIds))).all())
        for user in users:
            user.department_id = payload.departmentId
            user.updated_at = datetime.utcnow()
            self.session.add(user)
        self.session.commit()
        for user in users:
            clear_login_caches(user.id)
        return {"success": True}


class RoleAdminService(BaseAdminCrudService):
    """角色资源管理服务"""

    def list(self, query: CrudQuery | None = None) -> list[RoleRead]:
        statement = select(Role)
        statement = self._apply_query(statement, Role, query, fallback_field="created_at")
        roles = list(self.session.exec(statement).all())
        return [self._build_role_read(role) for role in roles]

    def page(self, query: CrudQuery) -> PageResult[RoleRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(Role)
        statement = self._apply_query(statement, Role, query, fallback_field="created_at")
        
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        roles = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_role_read(role) for role in roles],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> RoleRead:
        role = self.session.get(Role, id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        return self._build_role_read(role)

    def add(self, payload: RoleCreateRequest) -> RoleRead:
        role_code = payload.code or payload.label
        existing = self.session.exec(select(Role).where((Role.code == role_code) | (Role.label == payload.label))).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")
        role = Role(
            name=payload.name,
            code=role_code,
            label=payload.label,
            remark=payload.remark,
            data_scope="department" if payload.departmentIdList else "self",
            is_active=payload.status == 1,
            updated_at=datetime.utcnow(),
        )
        self.session.add(role)
        self.session.commit()
        self.session.refresh(role)
        self._replace_role_menus(role.id, payload.menuIdList)
        self._replace_role_departments(role.id, payload.departmentIdList)
        return self._build_role_read(role)

    def update(self, payload: RoleUpdateRequest) -> RoleRead:
        role = self.session.get(Role, payload.id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        duplicate = self.session.exec(
            select(Role).where((Role.id != payload.id) & ((Role.code == (payload.code or payload.label)) | (Role.label == payload.label)))
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色编码或标识已存在")

        role.name = payload.name
        role.code = payload.code or payload.label
        role.label = payload.label
        role.remark = payload.remark
        role.data_scope = "department" if payload.departmentIdList else "self"
        role.is_active = payload.status == 1
        role.updated_at = datetime.utcnow()
        self.session.add(role)
        self.session.commit()
        self.session.refresh(role)
        self._replace_role_menus(role.id, payload.menuIdList)
        self._replace_role_departments(role.id, payload.departmentIdList)
        self._clear_role_related_caches([role.id])
        return self._build_role_read(role)

    def delete(self, ids: list[int]) -> dict:
        if not ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少待删除的角色 ID")

        roles = list(self.session.exec(select(Role).where(Role.id.in_(ids))).all())
        if any(role.code == "admin" for role in roles):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除系统管理员角色")

        affected_user_ids = [link.user_id for link in self.session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(ids))).all()]
        for link in list(self.session.exec(select(UserRoleLink).where(UserRoleLink.role_id.in_(ids))).all()):
            self.session.delete(link)
        for link in list(self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id.in_(ids))).all()):
            self.session.delete(link)
        for link in list(self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id.in_(ids))).all()):
            self.session.delete(link)
        for role in roles:
            self.session.delete(role)
        self.session.commit()
        clear_login_caches_for_users(affected_user_ids)
        return {"success": True, "deleted_ids": ids}

    def assign_menus(self, payload: RoleMenuAssignRequest) -> dict:
        role = self.session.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        self._replace_role_menus(payload.role_id, payload.menu_ids)
        self._clear_role_related_caches([payload.role_id])
        return {"success": True, "role_id": payload.role_id, "menu_ids": payload.menu_ids}

    def _build_role_read(self, role: Role) -> RoleRead:
        menu_ids = [link.menu_id for link in self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role.id)).all()]
        department_ids = [
            link.department_id for link in self.session.exec(select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == role.id)).all()
        ]
        return RoleRead(
            id=role.id,
            name=role.name,
            label=role.label,
            code=role.code,
            remark=role.remark,
            status=1 if role.is_active else 0,
            relevance=1,
            menuIdList=menu_ids,
            departmentIdList=department_ids,
            createTime=role.created_at,
            updateTime=role.updated_at or role.created_at,
        )

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

    def list(self, query: CrudQuery | None = None) -> list[DepartmentRead]:
        statement = select(Department)
        statement = self._apply_query(statement, Department, query, fallback_field="sort_order")
        departments = list(self.session.exec(statement).all())
        return [self._build_department_read(item) for item in departments]

    def page(self, query: CrudQuery) -> PageResult[DepartmentRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(Department)
        statement = self._apply_query(statement, Department, query, fallback_field="sort_order")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        departments = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_department_read(item) for item in departments],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> DepartmentRead:
        department = self.session.get(Department, id)
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        return self._build_department_read(department)

    def add(self, payload: DepartmentCreateRequest) -> DepartmentRead:
        department = Department(
            parent_id=payload.parentId,
            name=payload.name,
            sort_order=payload.orderNum,
            is_active=True,
            updated_at=datetime.utcnow(),
        )
        self.session.add(department)
        self.session.commit()
        self.session.refresh(department)
        return self._build_department_read(department)

    def update(self, payload: DepartmentUpdateRequest) -> DepartmentRead:
        department = self.session.get(Department, payload.id)
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
        department.parent_id = payload.parentId
        department.name = payload.name
        department.sort_order = payload.orderNum
        department.updated_at = datetime.utcnow()
        self.session.add(department)
        self.session.commit()
        self.session.refresh(department)
        return self._build_department_read(department)

    def delete(self, ids: list[int], payload: DepartmentDeleteRequest | None = None) -> dict:
        if not ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少待删除的部门 ID")
        delete_user = bool(payload.deleteUser) if payload else False
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
                        user.updated_at = datetime.utcnow()
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
            department.parent_id = data.parentId
            department.sort_order = data.orderNum
            department.updated_at = datetime.utcnow()
            self.session.add(department)
        self.session.commit()
        return {"success": True}

    def _build_department_read(self, department: Department) -> DepartmentRead:
        parent = self.session.get(Department, department.parent_id) if department.parent_id else None
        return DepartmentRead(
            id=department.id,
            parentId=department.parent_id,
            name=department.name,
            parentName=parent.name if parent else None,
            orderNum=department.sort_order,
            status=1 if department.is_active else 0,
            createTime=department.created_at,
            updateTime=department.updated_at or department.created_at,
        )

    def _collect_descendant_department_ids(self, root_ids: list[int]) -> list[int]:
        all_departments = list(self.session.exec(select(Department)).all())
        children_map: dict[int | None, list[int]] = defaultdict(list)
        for department in all_departments:
            children_map[department.parent_id].append(department.id)
        result: set[int] = set()
        stack = list(root_ids)
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            stack.extend(children_map.get(current, []))
        return sorted(result)


class MenuAdminService(BaseAdminCrudService):
    """菜单资源管理服务"""

    def list(self, query: CrudQuery | None = None) -> list[MenuRead]:
        statement = select(Menu)
        statement = self._apply_query(statement, Menu, query, fallback_field="sort_order")
        menus = list(self.session.exec(statement).all())
        
        # 预加载父级名称
        parent_ids = {menu.parent_id for menu in menus if menu.parent_id is not None}
        parent_map = {}
        if parent_ids:
            parents = list(self.session.exec(select(Menu).where(Menu.id.in_(list(parent_ids)))).all())
            parent_map = {p.id: p.name for p in parents}
            
        return [self._build_menu_read(menu, parent_name=parent_map.get(menu.parent_id)) for menu in menus]

    def page(self, query: CrudQuery) -> PageResult[MenuRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(Menu)
        statement = self._apply_query(statement, Menu, query, fallback_field="sort_order")
        
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        
        menus = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        
        # 预加载父级名称
        parent_ids = {menu.parent_id for menu in menus if menu.parent_id is not None}
        parent_map = {}
        if parent_ids:
            parents = list(self.session.exec(select(Menu).where(Menu.id.in_(list(parent_ids)))).all())
            parent_map = {p.id: p.name for p in parents}
            
        return PageResult(
            items=[self._build_menu_read(menu, parent_name=parent_map.get(menu.parent_id)) for menu in menus],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> MenuRead:
        menu = self.session.get(Menu, id)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="菜单不存在")
        parent_name = None
        if menu.parent_id:
            parent = self.session.get(Menu, menu.parent_id)
            parent_name = parent.name if parent else None
        return self._build_menu_read(menu, parent_name=parent_name)

    def add(self, payload: MenuCreateRequest | list[MenuCreateRequest] | list[dict] | dict) -> MenuRead | list[MenuRead]:
        if isinstance(payload, list):
            created: list[MenuRead] = []
            for item in payload:
                data = item if isinstance(item, MenuCreateRequest) else MenuCreateRequest(**item)
                created.append(self.add(data))
            return created
        if isinstance(payload, dict):
            payload = MenuCreateRequest(**payload)
        code = payload.code or self._generate_menu_code(payload)
        existing = self.session.exec(select(Menu).where(Menu.code == code)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")
        menu = Menu(
            parent_id=payload.parentId,
            name=payload.name,
            code=code,
            type=self._normalize_menu_type(payload.type),
            path=payload.router,
            component=payload.viewPath,
            icon=payload.icon,
            keep_alive=payload.keepAlive,
            is_show=payload.isShow,
            permission=payload.perms,
            sort_order=payload.orderNum,
            is_active=payload.status == 1,
            updated_at=datetime.utcnow(),
        )
        self.session.add(menu)
        self.session.commit()
        self.session.refresh(menu)
        self._clear_menu_related_caches([menu.id])
        return self._build_menu_read(menu)

    def update(self, payload: MenuUpdateRequest) -> MenuRead:
        menu = self.session.get(Menu, payload.id)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="菜单不存在")
        normalized_code = payload.code or menu.code or self._generate_menu_code(payload)
        duplicate = self.session.exec(select(Menu).where((Menu.id != payload.id) & (Menu.code == normalized_code))).first()
        if duplicate and duplicate.code == normalized_code:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="菜单编码已存在")
        menu.parent_id = payload.parentId
        menu.name = payload.name
        menu.code = normalized_code
        menu.type = self._normalize_menu_type(payload.type)
        menu.path = payload.router
        menu.component = payload.viewPath
        menu.icon = payload.icon
        menu.keep_alive = payload.keepAlive
        menu.is_show = payload.isShow
        menu.permission = payload.perms
        menu.sort_order = payload.orderNum
        menu.is_active = payload.status == 1
        menu.updated_at = datetime.utcnow()
        self.session.add(menu)
        self.session.commit()
        self.session.refresh(menu)
        self._clear_menu_related_caches([menu.id])
        return self._build_menu_read(menu)

    def delete(self, ids: list[int]) -> dict:
        if not ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少待删除的菜单 ID")
        menu_ids = self._collect_descendant_menu_ids(ids)
        for link in list(self.session.exec(select(RoleMenuLink).where(RoleMenuLink.menu_id.in_(menu_ids))).all()):
            self.session.delete(link)
        for menu in list(self.session.exec(select(Menu).where(Menu.id.in_(menu_ids))).all()):
            self.session.delete(menu)
        self.session.commit()
        self._clear_menu_related_caches(menu_ids)
        return {"success": True, "deleted_ids": menu_ids}

    def tree(self) -> list[MenuTreeItem]:
        menus = list(self.session.exec(select(Menu).order_by(Menu.sort_order.asc(), Menu.created_at.asc())).all())
        return self._build_tree(menus)

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
        return [item.model_dump(mode="json") for item in result]

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
                        router=self._build_router_from_resource(module_name, resource),
                        viewPath=self._build_view_path_from_resource(module_name, resource),
                        icon=None,
                        parentCode=get_menu_parent_code(module_name, resource),
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
                    ).model_dump(mode="json")
                )
        items.sort(key=lambda entry: (entry["module"], entry["resource"], entry["router"]))
        return {"list": items}

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
            menu.id: MenuTreeItem(**self._build_menu_read(menu, parent_name=name_map.get(menu.parent_id)).model_dump())
            for menu in menus
        }
        children_map: dict[int | None, list[MenuTreeItem]] = defaultdict(list)
        for menu in menus:
            children_map[menu.parent_id].append(nodes[menu.id])
        for parent_id, children in children_map.items():
            children.sort(key=lambda item: (item.orderNum, item.createTime))
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

    def _build_tree(self, menus: list[Menu]) -> list[MenuTreeItem]:
        nodes = {
            menu.id: MenuTreeItem(**self._build_menu_read(menu).model_dump())
            for menu in menus
        }
        children_map: dict[int | None, list[MenuTreeItem]] = defaultdict(list)
        for menu in menus:
            children_map[menu.parent_id].append(nodes[menu.id])
        for parent_id, children in children_map.items():
            children.sort(key=lambda item: (item.orderNum, item.createTime))
            if parent_id in nodes:
                nodes[parent_id].children = children
        return children_map.get(None, [])

    def _collect_descendant_menu_ids(self, root_ids: list[int]) -> list[int]:
        all_menus = list(self.session.exec(select(Menu)).all())
        children_map: dict[int | None, list[int]] = defaultdict(list)
        for menu in all_menus:
            children_map[menu.parent_id].append(menu.id)

        result: set[int] = set()
        stack = list(root_ids)
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            stack.extend(children_map.get(current, []))
        return sorted(result)

    def _clear_menu_related_caches(self, menu_ids: list[int]) -> None:
        clear_login_caches_for_menus(self.session, menu_ids)

    def _menu_tree_to_import_node(self, node: MenuTreeItem) -> MenuImportNode:
        return MenuImportNode(
            id=node.id,
            parentId=node.parentId,
            name=node.name,
            router=node.router,
            viewPath=node.viewPath,
            perms=node.perms,
            type=node.type,
            icon=node.icon,
            orderNum=node.orderNum,
            keepAlive=node.keepAlive,
            isShow=node.isShow,
            childMenus=[self._menu_tree_to_import_node(child) for child in node.children],
        )

    def _upsert_import_node(self, node: MenuImportNode, parent_id: int | None) -> Menu:
        target = None
        if node.id:
            target = self.session.get(Menu, node.id)
        if target is None and node.router:
            target = self.session.exec(select(Menu).where(Menu.path == node.router, Menu.type == self._normalize_menu_type(node.type))).first()
        if target is None and node.perms:
            target = self.session.exec(select(Menu).where(Menu.permission == node.perms)).first()
        if target is None:
            target = Menu(code=self._generate_import_code(node), name=node.name)

        target.parent_id = parent_id
        target.name = node.name
        target.type = self._normalize_menu_type(node.type)
        target.path = node.router
        target.component = node.viewPath
        target.permission = node.perms
        target.icon = node.icon
        target.keep_alive = node.keepAlive
        target.is_show = node.isShow
        target.sort_order = node.orderNum
        target.is_active = True
        target.updated_at = datetime.utcnow()
        if not target.code:
            target.code = self._generate_import_code(node)
        self.session.add(target)
        self.session.flush()

        for child in node.childMenus:
            self._upsert_import_node(child, target.id)
        return target

    def _build_menu_read(self, menu: Menu, parent_name: str | None = None) -> MenuRead:
        type_mapping = {"group": 0, "menu": 1, "button": 2}
        return MenuRead(
            id=menu.id,
            parentId=menu.parent_id,
            parentName=parent_name,
            name=menu.name,
            code=menu.code,
            type=type_mapping.get(menu.type, 2),
            router=menu.path,
            viewPath=menu.component,
            icon=menu.icon,
            keepAlive=menu.keep_alive,
            isShow=menu.is_show,
            perms=menu.permission,
            orderNum=menu.sort_order,
            status=1 if menu.is_active else 0,
            createTime=menu.created_at,
            updateTime=menu.updated_at or menu.created_at,
        )

    @staticmethod
    def _normalize_menu_type(value: int | str) -> str:
        if value in (0, "0", "group", "dir"):
            return "group"
        if value in (1, "1", "menu"):
            return "menu"
        return "button"

    def _generate_menu_code(self, payload: MenuCreateRequest | MenuUpdateRequest) -> str:
        seed = payload.code or payload.router or payload.perms or payload.name
        return self._next_unique_code(self._slugify(seed))

    def _generate_import_code(self, node: MenuImportNode) -> str:
        seed = node.router or node.perms or node.name
        return self._next_unique_code(self._slugify(seed))

    @staticmethod
    def _build_view_path(item: MenuCreateAutoItem) -> str | None:
        if item.viewPath:
            return item.viewPath
        if item.module and item.router:
            suffix = item.router.replace(f"/{item.module}", "")
            return f"modules/{item.module}/views{suffix}.vue"
        return None

    @staticmethod
    def _build_auto_permission(item: MenuCreateAutoItem, path: str) -> str:
        prefix = (item.prefix or "").replace("/admin/", "")
        return f"{prefix}{path}".replace("/", ":").strip(":")

    def _upsert_auto_menu(self, item: MenuCreateAutoItem) -> Menu:
        menu = self.session.exec(select(Menu).where(Menu.path == item.router, Menu.type == "menu")).first()
        if menu is None:
            menu = Menu(code=self._next_unique_code(self._slugify(item.router or item.name)), name=item.name)

        menu.parent_id = item.parentId
        menu.name = item.name
        menu.type = "menu"
        menu.path = item.router
        menu.component = item.viewPath or self._build_view_path(item)
        menu.icon = item.icon
        menu.keep_alive = item.keepAlive
        menu.is_show = True
        menu.sort_order = item.orderNum
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
        if module == "task_ai":
            return "modules/task/views/list.vue"
        return f"modules/{module}/views/{resource.split('/')[-1]}.vue"

    @staticmethod
    def _build_permission_from_resource(module: str, resource: str, name: str | None, path: str | None) -> str | None:
        action = name or (path or "").rstrip("/").split("/")[-1]
        if not action:
            return None
        return f"{module}:{resource.replace('/', ':')}:{action}"
