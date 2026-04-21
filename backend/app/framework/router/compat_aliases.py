"""
cool-admin-vue 兼容路由别名
"""
from __future__ import annotations

from importlib import import_module
from typing import Iterable

from fastapi import APIRouter, Body, Depends, Query
from sqlmodel import Session, select

from app.modules.base.compat import RESOURCE_COMPATS

ROUTER_ALIASES: tuple[tuple[str, str], ...] = (
    ("app.modules.base.controller.admin.user", "/admin/base/sys/user"),
    ("app.modules.base.controller.admin.role", "/admin/base/sys/role"),
    ("app.modules.base.controller.admin.menu", "/admin/base/sys/menu"),
    ("app.modules.base.controller.admin.department", "/admin/base/sys/department"),
    ("app.modules.dict.controller.admin.type", "/admin/dict/type"),
    ("app.modules.dict.controller.admin.info", "/admin/dict/info"),
)


def register_compat_aliases(api_router: APIRouter) -> None:
    for module_path, prefix in ROUTER_ALIASES:
        try:
            route_module = import_module(module_path)
        except ModuleNotFoundError:
            continue
        router = getattr(route_module, "router", None)
        if router is not None:
            api_router.include_router(router, prefix=prefix)

    for compat in RESOURCE_COMPATS:
        controller_suffix = compat.source_resource.split("/")[-1]
        module_path = f"app.modules.{compat.source_module}.controller.admin.{controller_suffix}"
        try:
            route_module = import_module(module_path)
        except ModuleNotFoundError:
            continue
        router = getattr(route_module, "router", None)
        if router is None:
            continue
        for alias in compat.route_aliases:
            api_router.include_router(router, prefix=alias)

    api_router.include_router(_build_dict_compat_router())


def _build_dict_compat_router() -> APIRouter:
    router = APIRouter(prefix="/admin/dict/info", tags=["admin", "dict", "info"])

    @router.get("/types", summary="获取字典类型")
    async def dict_types(session: Session = Depends(_get_session)) -> list[dict]:
        from app.modules.base.model.sys import SysDict

        rows = list(session.exec(select(SysDict).order_by(SysDict.name.asc())).all())
        return [{"id": row.id, "key": row.type, "name": row.name} for row in rows]

    @router.get("/data", summary="批量获取字典数据")
    async def dict_data_get(
        types: list[str] = Query(default_factory=list),
        session: Session = Depends(_get_session),
    ) -> dict[str, list[dict]]:
        return _build_dict_data_payload(session, types)

    @router.post("/data", summary="批量获取字典数据")
    async def dict_data_post(
        payload: dict = Body(default_factory=dict),
        session: Session = Depends(_get_session),
    ) -> dict[str, list[dict]]:
        raw_types = payload.get("types") or []
        return _build_dict_data_payload(session, raw_types)

    return router


def _build_dict_data_payload(session: Session, raw_types: Iterable[str]) -> dict[str, list[dict]]:
    from app.modules.base.model.sys import SysDict, SysDictData

    types = [item for item in raw_types if item]
    if not types:
        dict_rows = list(session.exec(select(SysDict).order_by(SysDict.name.asc())).all())
        types = [item.type for item in dict_rows]

    if not types:
        return {}

    dict_rows = list(session.exec(select(SysDict).where(SysDict.type.in_(types))).all())
    dict_map = {item.id: item.type for item in dict_rows if item.id is not None}
    if not dict_map:
        return {}

    data_rows = list(
        session.exec(
            select(SysDictData).where(SysDictData.type_id.in_(dict_map.keys())).order_by(SysDictData.sort_order.asc())
        ).all()
    )
    result: dict[str, list[dict]] = {dict_type: [] for dict_type in types}
    for row in data_rows:
        dict_type = dict_map.get(row.type_id)
        if not dict_type:
            continue
        result.setdefault(dict_type, []).append(
            {
                "id": row.id,
                "parentId": None,
                "name": row.label,
                "label": row.label,
                "value": row.value,
                "orderNum": row.sort_order,
            }
        )
    return result


def _get_session():
    from app.core.database import get_session

    yield from get_session()
