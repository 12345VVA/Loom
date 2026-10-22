"""角色资产服务。"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.asset.model.asset import AssetCharacter
from app.modules.asset.service.base import AssetCrudServiceBase


class AssetCharacterService(AssetCrudServiceBase):
    def __init__(self, session: Session):
        super().__init__(session, AssetCharacter)
