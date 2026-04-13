"""
类似 cool-admin-midway 的装饰器式控制器元数据
"""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_session
from app.framework.router.route_meta import CoolRouteMeta, TagTypes, cool_tag, get_route_meta
from app.modules.base.model.auth import DeleteRequest, PageResult
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.module_config import PermissionConfig


@dataclass(frozen=True)
class CrudAction:
    name: str
    method: str
    path: str
    permission_suffix: str
    summary: str


@dataclass(frozen=True)
class ServiceApiConfig:
    method: str
    summary: str | None = None
    permission: str | None = None
    role_codes: tuple[str, ...] = ("admin",)


@dataclass(frozen=True)
class ExportedRouteMeta:
    scope: str
    module: str
    resource: str
    controller_name: str
    method: str
    path: str
    summary: str | None = None
    permission: str | None = None
    source: str = "custom"
    query_meta: dict[str, Any] = field(default_factory=dict)
    model: Any | None = None
    ignore_token: bool = False


@dataclass(frozen=True)
class QueryFieldConfig:
    column: str
    request_param: str | None = None


@dataclass(frozen=True)
class OrderByConfig:
    column: str
    direction: str = "desc"


@dataclass(frozen=True)
class QueryConfig:
    keyword_like_fields: tuple[str, ...] = field(default_factory=tuple)
    field_eq: tuple[str | QueryFieldConfig, ...] = field(default_factory=tuple)
    field_like: tuple[str | QueryFieldConfig, ...] = field(default_factory=tuple)
    add_order_by: tuple[OrderByConfig, ...] = field(default_factory=tuple)
    where: Any | None = None
    select: tuple[str, ...] = field(default_factory=tuple)
    keyword_fields: tuple[str, ...] = field(default_factory=tuple)
    eq_filters: tuple[str, ...] = field(default_factory=tuple)
    like_filters: tuple[str, ...] = field(default_factory=tuple)
    order_fields: tuple[str, ...] = field(default_factory=tuple)
    default_order: str | None = None
    default_sort: str = "desc"


@dataclass(frozen=True)
class CrudQuery:
    page: int | None = None
    size: int | None = None
    keyword: str | None = None
    order: str | None = None
    sort: str | None = None
    keyword_fields: tuple[str, ...] = field(default_factory=tuple)
    order_fields: tuple[str, ...] = field(default_factory=tuple)
    select_fields: tuple[str, ...] = field(default_factory=tuple)
    add_order_by: tuple[OrderByConfig, ...] = field(default_factory=tuple)
    where_handler: Any | None = None
    eq_filters: dict[str, Any] = field(default_factory=dict)
    like_filters: dict[str, Any] = field(default_factory=dict)
    raw_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BeforeHookConfig:
    action: str
    method: str


@dataclass(frozen=True)
class InsertParamConfig:
    target: str
    source: str
    action: str | None = None


DEFAULT_CRUD_ACTIONS: tuple[CrudAction, ...] = (
    CrudAction(name="list", method="GET", path="/list", permission_suffix="list", summary="获取列表"),
    CrudAction(name="page", method="GET", path="/page", permission_suffix="page", summary="获取分页"),
    CrudAction(name="info", method="GET", path="/info", permission_suffix="info", summary="获取详情"),
    CrudAction(name="add", method="POST", path="/add", permission_suffix="add", summary="新增"),
    CrudAction(name="update", method="POST", path="/update", permission_suffix="update", summary="更新"),
    CrudAction(name="delete", method="POST", path="/delete", permission_suffix="delete", summary="删除"),
)


@dataclass(frozen=True)
class CoolControllerMeta:
    module: str
    resource: str
    service: type
    description: str = ""
    controller_name: str | None = None
    scope: str = "admin"
    tags: tuple[str, ...] = field(default_factory=tuple)
    name_prefix: str = ""
    code_prefix: str = ""
    role_codes: tuple[str, ...] = ("admin",)
    actions: tuple[CrudAction | str, ...] = DEFAULT_CRUD_ACTIONS
    list_response_model: Any | None = None
    page_item_model: Any | None = None
    info_response_model: Any | None = None
    info_param_type: Any = int
    add_request_model: Any | None = None
    add_response_model: Any | None = None
    update_request_model: Any | None = None
    update_response_model: Any | None = None
    delete_request_model: Any = DeleteRequest
    list_query: QueryConfig | None = None
    page_query: QueryConfig | None = None
    before_hooks: tuple[BeforeHookConfig, ...] = field(default_factory=tuple)
    insert_params: tuple[InsertParamConfig, ...] = field(default_factory=tuple)
    info_ignore_property: tuple[str, ...] = field(default_factory=tuple)
    service_apis: tuple[ServiceApiConfig | str, ...] = field(default_factory=tuple)
    api: tuple[CrudAction | str, ...] | None = None
    entity: Any | None = None


class BaseController:
    """装饰器控制器基类。"""


class BaseCrudService:
    """CRUD 服务基类。"""

    def __init__(self, session: Session):
        self.session = session


_registered_permission_configs: list[PermissionConfig] = []
_registered_exported_routes: list[ExportedRouteMeta] = []


def get_registered_permission_configs() -> list[PermissionConfig]:
    return list(_registered_permission_configs)


def get_registered_exported_routes() -> list[ExportedRouteMeta]:
    return list(_registered_exported_routes)


def CoolController(meta: CoolControllerMeta):
    """装饰器式控制器声明。"""

    def decorator(cls):
        cool_tag(f"{TagTypes.SCOPE}:{meta.scope}")(cls)
        router = APIRouter(tags=[meta.scope, *meta.tags])
        controller = cls()

        _register_crud_routes(router, meta)
        _register_custom_routes(router, controller, meta)
        _register_service_routes(router, meta)

        cls.router = router
        cls.meta = meta
        return cls

    return decorator


def _register_crud_routes(router: APIRouter, meta: CoolControllerMeta) -> None:
    # 建立快捷查找映射
    default_actions_map = {action.name: action for action in DEFAULT_CRUD_ACTIONS}
    
    actions = meta.api or meta.actions
    controller_name = meta.controller_name or "".join(part.capitalize() for part in str(meta.resource).replace("/", ":").split(":"))

    for action_item in actions:
        # 支持字符串形式或对象形式
        if isinstance(action_item, str):
            action = default_actions_map.get(action_item)
            if not action:
                continue
        else:
            action = action_item

        permission = f"{meta.module}:{meta.resource.replace('/', ':')}:{action.permission_suffix}"
        full_path = f"/{meta.scope}/{meta.module}/{meta.resource}{action.path}"
        # 确定该资源对应的核心模型，用于 EPS 扫描列
        core_model = meta.page_item_model or meta.list_response_model or meta.info_response_model

        _registered_permission_configs.append(
            PermissionConfig(
                name=f"{meta.name_prefix}{action.summary}",
                code=f"{meta.code_prefix}_{action.permission_suffix}",
                permission=permission,
                admin_patterns=(f"{action.method} {full_path}",),
                role_codes=meta.role_codes,
            )
        )
        _registered_exported_routes.append(
            ExportedRouteMeta(
                scope=meta.scope,
                module=meta.module,
                resource=meta.resource,
                controller_name=controller_name,
                method=action.method,
                path=full_path,
                summary=action.summary,
                permission=permission,
                source="crud",
                query_meta=_export_query_meta(meta.page_query if action.name == "page" else meta.list_query),
                model=core_model,
                ignore_token=False,
            )
        )

        if action.name == "list":
            response_model = list[meta.list_response_model] if meta.list_response_model is not None else None

            async def endpoint(
                keyword: str | None = Query(default=None),
                order: str | None = Query(default=None),
                sort: str | None = Query(default=None),
                session: Session = Depends(get_session),
                request: Request = None,
                background_tasks: BackgroundTasks = None,
                current_user: User = Depends(get_current_user),
                _action_name: str = action.name,
            ):
                service = meta.service(session)
                query = _build_crud_query(
                    request=request,
                    config=meta.list_query,
                    keyword=keyword,
                    order=order,
                    sort=sort,
                )
                available_kwargs = _build_service_kwargs(
                    meta=meta,
                    action_name=_action_name,
                    query=query,
                    request=request,
                    background_tasks=background_tasks,
                    current_user=current_user,
                )
                _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                result = _invoke_service(
                    service.list,
                    **available_kwargs,
                )
                return await _resolve_result(result)

            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(
                action.path,
                endpoint,
                methods=[action.method],
                response_model=response_model,
                response_model_exclude_none=bool(meta.info_ignore_property),
                summary=action.summary,
            )
        elif action.name == "page":
            response_model = PageResult[meta.page_item_model] if meta.page_item_model is not None else None

            async def endpoint(
                page: int = Query(default=1, ge=1),
                size: int = Query(default=10, ge=1, le=100),
                keyword: str | None = Query(default=None),
                order: str | None = Query(default=None),
                sort: str | None = Query(default=None),
                session: Session = Depends(get_session),
                request: Request = None,
                background_tasks: BackgroundTasks = None,
                current_user: User = Depends(get_current_user),
                _action_name: str = action.name,
            ):
                service = meta.service(session)
                query = _build_crud_query(
                    request=request,
                    config=meta.page_query or meta.list_query,
                    page=page,
                    size=size,
                    keyword=keyword,
                    order=order,
                    sort=sort,
                )
                available_kwargs = _build_service_kwargs(
                    meta=meta,
                    action_name=_action_name,
                    query=query,
                    request=request,
                    background_tasks=background_tasks,
                    current_user=current_user,
                )
                _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                result = _invoke_service(
                    service.page,
                    **available_kwargs,
                )
                return await _resolve_result(result)

            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(action.path, endpoint, methods=[action.method], response_model=response_model, summary=action.summary)
        elif action.name == "info":
            response_model = meta.info_response_model
            if meta.info_param_type is int:

                async def endpoint(
                    id: int = Query(..., ge=1),
                    session: Session = Depends(get_session),
                    request: Request = None,
                    background_tasks: BackgroundTasks = None,
                    current_user: User = Depends(get_current_user),
                    _action_name: str = action.name,
                ):
                    service = meta.service(session)
                    available_kwargs = _build_service_kwargs(
                        meta=meta,
                        action_name=_action_name,
                        id=id,
                        request=request,
                        background_tasks=background_tasks,
                        current_user=current_user,
                    )
                    _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                    result = _invoke_service(
                        service.info,
                        **available_kwargs,
                    )
                    return _strip_ignored_properties(await _resolve_result(result), meta.info_ignore_property)
            else:

                async def endpoint(
                    id: str = Query(...),
                    session: Session = Depends(get_session),
                    request: Request = None,
                    background_tasks: BackgroundTasks = None,
                    current_user: User = Depends(get_current_user),
                    _action_name: str = action.name,
                ):
                    service = meta.service(session)
                    available_kwargs = _build_service_kwargs(
                        meta=meta,
                        action_name=_action_name,
                        id=id,
                        request=request,
                        background_tasks=background_tasks,
                        current_user=current_user,
                    )
                    _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                    result = _invoke_service(
                        service.info,
                        **available_kwargs,
                    )
                    return _strip_ignored_properties(await _resolve_result(result), meta.info_ignore_property)

            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(action.path, endpoint, methods=[action.method], response_model=response_model, summary=action.summary)
        elif action.name == "add":
            request_model = meta.add_request_model
            response_model = meta.add_response_model

            async def endpoint(
                payload,
                session: Session = Depends(get_session),
                request: Request = None,
                background_tasks: BackgroundTasks = None,
                current_user: User = Depends(get_current_user),
                _action_name: str = action.name,
            ):
                service = meta.service(session)
                available_kwargs = _build_service_kwargs(
                    meta=meta,
                    action_name=_action_name,
                    payload=payload,
                    request=request,
                    background_tasks=background_tasks,
                    current_user=current_user,
                )
                _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                result = _invoke_service(
                    service.add,
                    **available_kwargs,
                )
                return await _resolve_result(result)

            endpoint.__annotations__["payload"] = request_model
            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(action.path, endpoint, methods=[action.method], response_model=response_model, summary=action.summary)
        elif action.name == "update":
            request_model = meta.update_request_model
            response_model = meta.update_response_model

            async def endpoint(
                payload,
                session: Session = Depends(get_session),
                request: Request = None,
                background_tasks: BackgroundTasks = None,
                current_user: User = Depends(get_current_user),
                _action_name: str = action.name,
            ):
                service = meta.service(session)
                available_kwargs = _build_service_kwargs(
                    meta=meta,
                    action_name=_action_name,
                    payload=payload,
                    request=request,
                    background_tasks=background_tasks,
                    current_user=current_user,
                )
                _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                result = _invoke_service(
                    service.update,
                    **available_kwargs,
                )
                return await _resolve_result(result)

            endpoint.__annotations__["payload"] = request_model
            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(action.path, endpoint, methods=[action.method], response_model=response_model, summary=action.summary)
        elif action.name == "delete":
            request_model = meta.delete_request_model

            async def endpoint(
                payload,
                session: Session = Depends(get_session),
                request: Request = None,
                background_tasks: BackgroundTasks = None,
                current_user: User = Depends(get_current_user),
                _action_name: str = action.name,
            ):
                service = meta.service(session)
                available_kwargs = _build_service_kwargs(
                    meta=meta,
                    action_name=_action_name,
                    ids=payload.ids,
                    payload=payload,
                    request=request,
                    background_tasks=background_tasks,
                    current_user=current_user,
                )
                _run_before_hooks(service, meta.before_hooks, _action_name, available_kwargs)
                result = _invoke_service(
                    service.delete,
                    **available_kwargs,
                )
                return await _resolve_result(result)

            endpoint.__annotations__["payload"] = request_model
            _tag_generated_endpoint(endpoint, meta.scope)
            router.add_api_route(action.path, endpoint, methods=[action.method], response_model=dict, summary=action.summary)


def _register_custom_routes(router: APIRouter, controller: BaseController, meta: CoolControllerMeta) -> None:
    controller_name = meta.controller_name or "".join(part.capitalize() for part in str(meta.resource).replace("/", ":").split(":"))
    for attribute_name in dir(controller.__class__):
        if attribute_name.startswith("_"):
            continue
        method = getattr(controller, attribute_name)
        route_meta = get_route_meta(method)
        if route_meta is None:
            continue
        _register_custom_permission(meta, route_meta)
        _registered_exported_routes.append(
            ExportedRouteMeta(
                scope=meta.scope,
                module=meta.module,
                resource=meta.resource,
                controller_name=controller_name,
                method=route_meta.method,
                path=f"/{meta.scope}/{meta.module}/{meta.resource}{route_meta.path}",
                summary=route_meta.summary,
                permission=route_meta.permission,
                source="custom",
                query_meta={},
                ignore_token=route_meta.anonymous,
            )
        )
        router.add_api_route(
            route_meta.path,
            method,
            methods=[route_meta.method],
            summary=route_meta.summary,
        )


def _register_custom_permission(controller_meta: CoolControllerMeta, route_meta: CoolRouteMeta) -> None:
    if not route_meta.permission:
        return
    _registered_permission_configs.append(
        PermissionConfig(
            name=route_meta.summary or route_meta.permission,
            code=route_meta.permission.replace(":", "_").replace("/", "_"),
            permission=route_meta.permission.replace("/", ":"),
            admin_patterns=(f"{route_meta.method} /{controller_meta.scope}/{controller_meta.module}/{controller_meta.resource}{route_meta.path}",),
            role_codes=route_meta.role_codes,
        )
    )


def _register_service_routes(router: APIRouter, meta: CoolControllerMeta) -> None:
    controller_name = meta.controller_name or "".join(part.capitalize() for part in str(meta.resource).replace("/", ":").split(":"))
    for item in meta.service_apis:
        config = item if isinstance(item, ServiceApiConfig) else ServiceApiConfig(method=item)
        permission = config.permission or f"{meta.module}:{meta.resource.replace('/', ':')}:{config.method}"
        full_path = f"/{meta.scope}/{meta.module}/{meta.resource}/{config.method}"
        _registered_permission_configs.append(
            PermissionConfig(
                name=config.summary or config.method,
                code=permission.replace(":", "_").replace("/", "_"),
                permission=permission.replace("/", ":"),
                admin_patterns=(f"POST {full_path}",),
                role_codes=config.role_codes,
            )
        )
        _registered_exported_routes.append(
            ExportedRouteMeta(
                scope=meta.scope,
                module=meta.module,
                resource=meta.resource,
                controller_name=controller_name,
                method="POST",
                path=full_path,
                summary=config.summary or config.method,
                permission=permission,
                source="service",
                query_meta={},
                ignore_token=False,
            )
        )

        async def endpoint(
            payload: dict[str, Any] = Body(default_factory=dict),
            session: Session = Depends(get_session),
            request: Request = None,
            background_tasks: BackgroundTasks = None,
            current_user: User = Depends(get_current_user),
            _service_method: str = config.method,
        ):
            service = meta.service(session)
            method = getattr(service, _service_method)
            available_kwargs = _build_service_kwargs(
                meta=meta,
                action_name=_service_method,
                payload=payload,
                params=payload,
                request=request,
                background_tasks=background_tasks,
                current_user=current_user,
            )
            _run_before_hooks(service, meta.before_hooks, _service_method, available_kwargs)
            result = _invoke_service(
                method,
                **available_kwargs,
            )
            return await _resolve_result(result)

        _tag_generated_endpoint(endpoint, meta.scope)
        router.add_api_route(f"/{config.method}", endpoint, methods=["POST"], summary=config.summary or config.method)


def _tag_generated_endpoint(endpoint, scope: str) -> None:
    cool_tag(f"{TagTypes.SCOPE}:{scope}")(endpoint)


def _invoke_service(method, **available_kwargs):
    signature = inspect.signature(method)
    kwargs = {
        name: value
        for name, value in available_kwargs.items()
        if name in signature.parameters
    }
    return method(**kwargs)


def _build_service_kwargs(meta: CoolControllerMeta, action_name: str, **available_kwargs):
    kwargs = dict(available_kwargs)
    for item in meta.insert_params:
        if item.action and item.action != action_name:
            continue
        source_value = _resolve_path(kwargs, item.source)
        if source_value is _MISSING:
            continue
        _assign_path(kwargs, item.target, source_value)
    kwargs["action_name"] = action_name
    return kwargs


def _build_crud_query(
    *,
    request: Request | None,
    config: QueryConfig | None,
    page: int | None = None,
    size: int | None = None,
    keyword: str | None = None,
    order: str | None = None,
    sort: str | None = None,
) -> CrudQuery:
    config = config or QueryConfig()
    eq_filters: dict[str, Any] = {}
    like_filters: dict[str, Any] = {}
    raw_params: dict[str, Any] = {}
    reserved = {"page", "size", "pageSize", "page_size", "keyword", "order", "sort"}
    eq_mappings = _normalize_query_fields((*config.field_eq, *config.eq_filters))
    like_mappings = _normalize_query_fields((*config.field_like, *config.like_filters))

    if request is not None:
        # 获取所有唯一参数名
        for key in set(request.query_params.keys()):
            if key in reserved:
                continue
            
            # 使用 getlist 获取所有重复项的值，支持多个相同 key 的情况 (适配 IN 查询)
            values = request.query_params.getlist(key)
            if not values or (len(values) == 1 and values[0] == ""):
                continue
                
            val = values[0] if len(values) == 1 else values
            raw_params[key] = val
            
            # 基础过滤映射
            if key in eq_mappings:
                eq_filters[eq_mappings[key]] = val
            if key in like_mappings:
                like_filters[like_mappings[key]] = val

    if request is not None:
        raw_size = request.query_params.get("size") or request.query_params.get("pageSize") or request.query_params.get("page_size")
        if raw_size and raw_size.isdigit():
            size = int(raw_size)

    return CrudQuery(
        page=page,
        size=size,
        keyword=keyword,
        order=order or config.default_order,
        sort=(sort or config.default_sort or "desc").lower(),
        keyword_fields=config.keyword_like_fields or config.keyword_fields,
        order_fields=config.order_fields,
        select_fields=config.select,
        add_order_by=config.add_order_by,
        where_handler=config.where,
        eq_filters=eq_filters,
        like_filters=like_filters,
        raw_params=raw_params,
    )


def _run_before_hooks(service, hooks: tuple[BeforeHookConfig, ...], action_name: str, available_kwargs: dict[str, Any]) -> None:
    for hook in hooks:
        if hook.action != action_name:
            continue
        method = getattr(service, hook.method)
        _invoke_service(method, **available_kwargs)


def _strip_ignored_properties(result: Any, ignored_properties: tuple[str, ...]) -> Any:
    if not ignored_properties or result is None:
        return result
    if hasattr(result, "model_dump"):
        data = result.model_dump(mode="json")
    elif isinstance(result, dict):
        data = dict(result)
    else:
        return result
    for key in ignored_properties:
        data.pop(key, None)
    return data


def _normalize_query_fields(fields: tuple[str | QueryFieldConfig, ...]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for item in fields:
        if isinstance(item, QueryFieldConfig):
            mappings[item.request_param or item.column] = item.column
        else:
            mappings[item] = item
    return mappings


def _export_query_meta(config: QueryConfig | None) -> dict[str, Any]:
    if config is None:
        return {}
    return {
        "keywordLikeFields": list(config.keyword_like_fields or config.keyword_fields),
        "fieldEq": [
            {"column": item.column, "requestParam": item.request_param or item.column}
            if isinstance(item, QueryFieldConfig)
            else {"column": item, "requestParam": item}
            for item in (*config.field_eq, *config.eq_filters)
        ],
        "fieldLike": [
            {"column": item.column, "requestParam": item.request_param or item.column}
            if isinstance(item, QueryFieldConfig)
            else {"column": item, "requestParam": item}
            for item in (*config.field_like, *config.like_filters)
        ],
        "addOrderBy": [
            {"column": item.column, "direction": item.direction}
            for item in config.add_order_by
        ],
        "select": list(config.select),
        "hasWhere": config.where is not None,
    }


_MISSING = object()


def _resolve_path(source: dict[str, Any], path: str):
    current: Any = source
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        else:
            if not hasattr(current, part):
                return _MISSING
            current = getattr(current, part)
    return current


def _assign_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = target
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return
    leaf = parts[-1]
    if isinstance(current, dict):
        current[leaf] = value
    elif hasattr(current, leaf):
        setattr(current, leaf, value)


async def _resolve_result(result):
    if inspect.isawaitable(result):
        return await result
    return result
