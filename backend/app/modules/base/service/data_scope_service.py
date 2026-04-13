"""
Base 模块数据权限服务
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from app.modules.base.model.auth import Department, RoleDepartmentLink, User
from app.modules.base.service.authority_service import get_user_roles, is_super_admin


@dataclass(frozen=True)
class DataScopeContext:
    allow_all: bool = False
    allowed_department_ids: frozenset[int] = frozenset()
    self_only: bool = True


def resolve_data_scope(session: Session, user: User) -> DataScopeContext:
    if is_super_admin(session, user):
        return DataScopeContext(allow_all=True, self_only=False)

    roles = get_user_roles(session, user.id)
    if not roles:
        return DataScopeContext(self_only=True)

    scopes = {role.data_scope for role in roles if role.is_active}
    if "all" in scopes:
        return DataScopeContext(allow_all=True, self_only=False)

    department_ids: set[int] = set()
    if "department" in scopes and user.department_id is not None:
        department_ids.update(_collect_department_descendants(session, [user.department_id]))

    if "custom" in scopes:
        linked_department_ids = [
            link.department_id
            for link in session.exec(
                select(RoleDepartmentLink).where(RoleDepartmentLink.role_id.in_([role.id for role in roles if role.id is not None]))
            ).all()
        ]
        if linked_department_ids:
            department_ids.update(_collect_department_descendants(session, linked_department_ids))

    if department_ids:
        return DataScopeContext(
            allow_all=False,
            allowed_department_ids=frozenset(department_ids),
            self_only=False,
        )

    return DataScopeContext(self_only=True)


def can_access_user(session: Session, current_user: User, target_user: User) -> bool:
    context = resolve_data_scope(session, current_user)
    if context.allow_all:
        return True
    if target_user.id == current_user.id:
        return True
    if context.allowed_department_ids and target_user.department_id in context.allowed_department_ids:
        return True
    return False


def _collect_department_descendants(session: Session, root_ids: list[int]) -> set[int]:
    departments = list(session.exec(select(Department).where(Department.is_active == True)).all())  # noqa: E712
    children_map: dict[int | None, list[int]] = {}
    for department in departments:
        children_map.setdefault(department.parent_id, []).append(department.id)

    result: set[int] = set()
    stack = list(root_ids)
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children_map.get(current, []))
    return result
