"""
字典数据接口
"""
from fastapi import Depends
from sqlmodel import Session
from app.core.database import get_session
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig, QueryFieldConfig
from app.framework.router.route_meta import Get, Post
from app.modules.dict.model.dict import DictInfoCreateRequest, DictInfoRead, DictInfoUpdateRequest
from app.modules.dict.service.dict_service import DictInfoService

@CoolController(
    CoolControllerMeta(
        module="dict",
        resource="info",
        scope="admin",
        service=DictInfoService,
        tags=("dict", "info"),
        code_prefix="dict_info",
        list_response_model=DictInfoRead,
        page_item_model=DictInfoRead,
        info_response_model=DictInfoRead,
        add_request_model=DictInfoCreateRequest,
        add_response_model=DictInfoRead,
        update_request_model=DictInfoUpdateRequest,
        update_response_model=DictInfoRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        list_query=QueryConfig(
            keyword_like_fields=("name",),
            field_eq=(QueryFieldConfig("type_id", "typeId"), QueryFieldConfig("parent_id", "parentId")),
            field_like=("name",),
            order_fields=("order_num", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("order_num", "asc"), OrderByConfig("created_at", "asc")),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name",),
            field_eq=(QueryFieldConfig("type_id", "typeId"), QueryFieldConfig("parent_id", "parentId")),
            field_like=("name",),
            order_fields=("order_num", "created_at", "updated_at", "name"),
            add_order_by=(OrderByConfig("order_num", "asc"), OrderByConfig("created_at", "asc")),
        ),
    )
)
class DictInfoController(BaseController):
    @Post("/data", summary="获得字典数据")
    async def data(
        self,
        payload: dict | None = None,
        session: Session = Depends(get_session),
    ) -> dict:
        types = (payload or {}).get("types") or []
        return DictInfoService(session).data(types)

    @Get("/types", summary="获得所有字典类型", anonymous=True)
    async def types(
        self,
        session: Session = Depends(get_session),
    ) -> list[dict]:
        return DictInfoService(session).types()

router = DictInfoController.router
