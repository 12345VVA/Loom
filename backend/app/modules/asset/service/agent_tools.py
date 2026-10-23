"""asset 模块的智能体工具（首版封闭清单 D11）。

结构契约见 app/modules/agent/service/agent_tools.py 模块 docstring——本模块**零 import agent**，
ctx 为鸭子类型（须提供 db/user_id/is_super_admin）。查询按调用者可见性过滤：
draft 仅创建者可见，管理员全量（与 asset CRUD 管理面同口径）。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel
from sqlmodel import Session, or_, select

from app.modules.asset.model.asset import (
    AssetCharacter,
    AssetScene,
    AssetStyle,
)


class QueryAssetArgs(BaseModel):
    """按标识查询资产信息。"""

    asset_type: Literal["character", "scene", "style"]
    asset_id: int | None = None
    code: str | None = None


def _visible_filter(model: type, user_id: int, is_super_admin: bool):
    if is_super_admin:
        return model.delete_time == None  # noqa: E711
    return or_(model.status != "draft", model.created_by == user_id)


def query_asset(args: QueryAssetArgs, ctx: Any) -> str:
    """查询 IP 资产（角色/场景/风格）的档案信息：按 id 或 code 定位，单条返回。"""
    model = {"character": AssetCharacter, "scene": AssetScene, "style": AssetStyle}[args.asset_type]
    session: Session = ctx.db
    statement = select(model).where(_visible_filter(model, ctx.user_id, ctx.is_super_admin))
    if args.asset_id is not None:
        statement = statement.where(model.id == args.asset_id)
    elif args.code:
        statement = statement.where(model.code == args.code)
    else:
        return json.dumps({"error": "asset_id 与 code 至少提供一个"}, ensure_ascii=False)

    entity = session.exec(statement).first()
    if entity is None:
        return json.dumps(
            {"found": False, "assetType": args.asset_type, "message": "未找到可见的匹配资产（不存在或无权查看）"},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "found": True,
            "id": entity.id,
            "code": entity.code,
            "name": entity.name,
            "assetType": args.asset_type,
            "status": entity.status,
            "category": entity.category,
            "appearancePrompt": entity.appearance_prompt,
            "negativePrompt": entity.negative_prompt,
        },
        ensure_ascii=False,
    )


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "query_asset",
            "description": "按 id 或编号查询 IP 资产（角色/场景/风格）的档案信息，仅返回调用者有权查看的资产",
            "level": "readonly",
            "args_model": QueryAssetArgs,
            "func": query_asset,
        },
    ]
