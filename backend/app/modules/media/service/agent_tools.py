"""media 模块的智能体工具（首版封闭清单 D11）。

结构契约见 app/modules/agent/service/agent_tools.py 模块 docstring——本模块**零 import agent**，
ctx 为鸭子类型。仅检索生成成功（status=success）的媒体资产，返回描述性元信息。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, or_, select

from app.modules.media.model.media import MediaAsset

_MAX_PAGE_SIZE = 50


class SearchMediaArgs(BaseModel):
    """关键词搜索媒体库。"""

    keyword: str = Field(min_length=1, max_length=100)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=_MAX_PAGE_SIZE)


def search_media(args: SearchMediaArgs, ctx: Any) -> str:
    """搜索媒体资产（按文件名/生成提示词匹配），返回描述性元信息列表。"""
    session: Session = ctx.db
    like = f"%{args.keyword}%"
    conditions = (
        MediaAsset.status == "success",
        MediaAsset.delete_time == None,  # noqa: E711
        or_(MediaAsset.file_name.like(like), MediaAsset.prompt.like(like)),
    )
    total = session.exec(select(func.count(MediaAsset.id)).where(*conditions)).one()
    rows = session.exec(
        select(MediaAsset).where(*conditions).offset((args.page - 1) * args.page_size).limit(args.page_size)
    ).all()
    return json.dumps(
        {
            "total": total,
            "page": args.page,
            "pageSize": args.page_size,
            "items": [
                {
                    "id": row.id,
                    "fileName": row.file_name,
                    "assetType": row.asset_type,
                    "mimeType": row.mime_type,
                    "width": row.width,
                    "height": row.height,
                    "prompt": (row.prompt or "")[:200],
                }
                for row in rows
            ],
        },
        ensure_ascii=False,
    )


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "search_media",
            "description": "按关键词搜索媒体库（文件名/生成提示词），返回媒体资产元信息列表",
            "level": "readonly",
            "args_model": SearchMediaArgs,
            "func": search_media,
        },
    ]
