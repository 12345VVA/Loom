"""IP 资产库场景管理 API。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.modules.asset.model.asset import (
    AssetSceneCreateRequest,
    AssetSceneRead,
    AssetSceneUpdateRequest,
)
from app.modules.asset.service.scene_service import AssetSceneService


@CoolController(
    CoolControllerMeta(
        module="asset",
        resource="scene",
        scope="admin",
        service=AssetSceneService,
        tags=("asset", "scene"),
        code_prefix="asset_scene",
        list_response_model=AssetSceneRead,
        page_item_model=AssetSceneRead,
        info_response_model=AssetSceneRead,
        add_request_model=AssetSceneCreateRequest,
        add_response_model=AssetSceneRead,
        update_request_model=AssetSceneUpdateRequest,
        update_response_model=AssetSceneRead,
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
class AssetSceneController(BaseController):
    pass


router = AssetSceneController.router
