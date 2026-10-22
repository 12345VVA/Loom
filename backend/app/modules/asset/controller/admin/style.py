"""IP 资产库风格管理 API。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.asset.model.asset import (
    AssetStyleCreateRequest,
    AssetStyleRead,
    AssetStyleUpdateRequest,
)
from app.modules.asset.service.style_service import AssetStyleService


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="style",
        scope="admin",
        service=AssetStyleService,
        tags=("asset", "style"),
        code_prefix="asset_style",
        list_response_model=AssetStyleRead,
        page_item_model=AssetStyleRead,
        info_response_model=AssetStyleRead,
        add_request_model=AssetStyleCreateRequest,
        add_response_model=AssetStyleRead,
        update_request_model=AssetStyleUpdateRequest,
        update_response_model=AssetStyleRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("name", "code"),
            field_like=(QueryFieldConfig("tags", "tags"),),
            field_eq=(
                QueryFieldConfig("status", "status"),
                QueryFieldConfig("category", "category"),
            ),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class AssetStyleController(BaseController):
    pass


router = AssetStyleController.router
