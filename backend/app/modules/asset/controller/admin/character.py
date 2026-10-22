"""IP 资产库角色管理 API。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.asset.model.asset import (
    AssetCharacterCreateRequest,
    AssetCharacterRead,
    AssetCharacterUpdateRequest,
)
from app.modules.asset.service.character_service import AssetCharacterService


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="character",
        scope="admin",
        service=AssetCharacterService,
        tags=("asset", "character"),
        code_prefix="asset_character",
        list_response_model=AssetCharacterRead,
        page_item_model=AssetCharacterRead,
        info_response_model=AssetCharacterRead,
        add_request_model=AssetCharacterCreateRequest,
        add_response_model=AssetCharacterRead,
        update_request_model=AssetCharacterUpdateRequest,
        update_response_model=AssetCharacterRead,
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
class AssetCharacterController(BaseController):
    pass


router = AssetCharacterController.router
