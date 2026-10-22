"""风格资产服务。"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.asset.model.asset import AssetStyle
from app.modules.asset.service.base import AssetCrudServiceBase


class AssetStyleService(AssetCrudServiceBase):
    resource_name = "style"

    def __init__(self, session: Session):
        super().__init__(session, AssetStyle)
