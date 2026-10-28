"""asset 模块的智能体工具（首版封闭清单 D11 + E3 可逆写首批）。

结构契约见 app/modules/agent/service/agent_tools.py 模块 docstring——本模块**零 import agent**，
ctx 为鸭子类型（须提供 db/user_id/is_super_admin）。查询按调用者可见性过滤：
draft 仅创建者可见，管理员全量（与 asset CRUD 管理面同口径）。
E3 写工具（reversible_write）：仅 draft 态 + 属主/管理员可写；safety 机制表声明可逆性与边界。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, or_, select

from app.modules.asset.model.asset import (
    ASSET_STATUS_DRAFT,
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


class CreateAssetDraftArgs(BaseModel):
    """创建资产草稿的入参（name 必填，其余可选）。"""

    asset_type: Literal["character", "scene", "style"]
    name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    appearance_prompt: str | None = None
    negative_prompt: str | None = None


class UpdateAssetDraftArgs(BaseModel):
    """编辑本人 draft 资产的入参（仅出现的字段被更新）。"""

    asset_type: Literal["character", "scene", "style"]
    asset_id: int
    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    appearance_prompt: str | None = None
    negative_prompt: str | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


_ASSET_MODELS = {"character": AssetCharacter, "scene": AssetScene, "style": AssetStyle}


def _load_owned_draft(ctx: Any, asset_type: str, asset_id: int):
    """加载 draft 态且调用者可写的资产（属主本人；管理员对他人草稿只读——写同样拒绝）。"""
    model = _ASSET_MODELS[asset_type]
    session: Session = ctx.db
    entity = session.get(model, asset_id)
    if entity is None or entity.delete_time is not None:
        return None, f"未找到资产（{asset_type}:{asset_id}）"
    if entity.status != ASSET_STATUS_DRAFT:
        return None, f"资产 {entity.code} 为 {entity.status} 态，仅 draft 态可编辑"
    if entity.created_by != ctx.user_id and not ctx.is_super_admin:
        return None, "仅资产创建者可编辑草稿"
    return entity, None


def create_asset_draft(args: CreateAssetDraftArgs, ctx: Any) -> str:
    """创建 draft 态资产草稿：code 自动生成（照 asset add 先例），不进发布流程。"""
    from app.modules.asset.service.base import AssetCrudServiceBase

    model = _ASSET_MODELS[args.asset_type]
    session: Session = ctx.db

    class _Caller:
        id = ctx.user_id
        is_super_admin = bool(ctx.is_super_admin)
        name = getattr(ctx, "user_name", "") or ""

    service = AssetCrudServiceBase(session, model)
    service.resource_name = args.asset_type
    entity = service.add(
        {
            "name": args.name,
            "category": args.category,
            "appearance_prompt": args.appearance_prompt,
            "negative_prompt": args.negative_prompt,
        },
        current_user=_Caller(),  # type: ignore[arg-type]
    )
    ctx.audit_target_ref = f"{args.asset_type}:{entity.id}"  # E3 审计：写操作目标引用
    return json.dumps(
        {"created": True, "id": entity.id, "code": entity.code, "name": entity.name, "status": entity.status},
        ensure_ascii=False,
    )


def update_asset_draft(args: UpdateAssetDraftArgs, ctx: Any) -> str:
    """编辑本人 draft 态资产：仅出现的字段被更新；published/archived 一律拒绝。"""
    entity, error = _load_owned_draft(ctx, args.asset_type, args.asset_id)
    if error is not None:
        return json.dumps({"updated": False, "error": error}, ensure_ascii=False)
    changes: dict = {}
    for field in ("name", "category", "appearance_prompt", "negative_prompt"):
        value = getattr(args, field)
        if value is not None:
            setattr(entity, field, value)
            changes[field] = True
    if args.tags is not None:
        entity.tags = json.dumps([t.strip() for t in args.tags if t.strip()], ensure_ascii=False)
        changes["tags"] = True
    if not changes:
        return json.dumps({"updated": False, "error": "未提供任何待更新字段"}, ensure_ascii=False)
    ctx.db.add(entity)
    ctx.db.commit()
    ctx.audit_target_ref = f"{args.asset_type}:{entity.id}"
    return json.dumps(
        {"updated": True, "id": entity.id, "code": entity.code, "name": entity.name, "changed": sorted(changes)},
        ensure_ascii=False,
    )


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "query_asset",
            "display_name": "查询资产",
            "description": "按 id 或编号查询 IP 资产（角色/场景/风格）的档案信息，仅返回调用者有权查看的资产",
            "level": "readonly",
            "args_model": QueryAssetArgs,
            "func": query_asset,
        },
        {
            "name": "create_asset_draft",
            "display_name": "创建资产草稿",
            "description": "创建 IP 资产草稿（角色/场景/风格），初始为草稿态不进入发布流程；仅创建可见的草稿底稿",
            "level": "reversible_write",
            "args_model": CreateAssetDraftArgs,
            "func": create_asset_draft,
            "safety": {
                "reversible_how": "创建物为 draft 态且不参与发布流程，可随时软删或弃置，不影响既有资产",
                "concurrency": "创建类操作无覆盖风险；code 自动生成含冲突重试",
                "audit_ref": "返回并记录 asset:{id}",
            },
        },
        {
            "name": "update_asset_draft",
            "display_name": "更新资产草稿",
            "description": "编辑调用者本人的 draft 态资产字段（名称/类别/外貌与负面提示词/标签）；已发布或归档资产不可改",
            "level": "reversible_write",
            "args_model": UpdateAssetDraftArgs,
            "func": update_asset_draft,
            "safety": {
                "reversible_how": "仅 draft 态可编辑（发布态拒绝），字段级修改可再次编辑覆盖回退",
                "concurrency": "draft 仅创建者可编辑（管理员只读他人草稿），并发面收敛到同一人",
                "audit_ref": "返回并记录 asset:{id}",
            },
        },
    ]
