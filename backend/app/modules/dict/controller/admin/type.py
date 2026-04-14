"""
字典类型接口
"""
from app.framework.controller_meta import BaseController, CoolController, CoolControllerMeta, OrderByConfig, QueryConfig
from app.modules.dict.service.dict_service import DictTypeService
from app.modules.dict.model.dict import DictTypeRead, DictTypeCreateRequest, DictTypeUpdateRequest

@CoolController(
    CoolControllerMeta(
        module="dict",
        resource="type",
        scope="admin",
        service=DictTypeService,
        tags=("dict", "type"),
        code_prefix="dict_type",
        list_response_model=DictTypeRead,
        page_item_model=DictTypeRead,
        info_response_model=DictTypeRead,
        add_request_model=DictTypeCreateRequest,
        add_response_model=DictTypeRead,
        update_request_model=DictTypeUpdateRequest,
        update_response_model=DictTypeRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        list_query=QueryConfig(
            keyword_like_fields=("name", "key"),
            field_like=("name", "key"),
            order_fields=("created_at", "updated_at", "name", "key"),
            add_order_by=(OrderByConfig("created_at", "asc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("name", "key"),
            field_like=("name", "key"),
            order_fields=("created_at", "updated_at", "name", "key"),
            add_order_by=(OrderByConfig("created_at", "asc"),),
        ),
        soft_delete=True,
    )
)
class DictTypeController(BaseController):
    pass

router = DictTypeController.router
