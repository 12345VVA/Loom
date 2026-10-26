"""media 模块的智能体工具（首版封闭清单 D11 + E3 可逆写首批）。

结构契约见 app/modules/agent/service/agent_tools.py 模块 docstring——本模块**零 import agent**，
ctx 为鸭子类型。检索仅看生成成功（status=success）的媒体资产；E3 写工具（reversible_write）
仅属主/管理员可操作，rename/tag 携 expected_updated_at 乐观比对防并发覆盖。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, or_, select

from app.modules.media.model.media import MediaAsset

_MAX_PAGE_SIZE = 50
_MAX_TAGS = 20
_MAX_TAG_LEN = 50


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
                    # E3：乐观比对锚点（rename/tag 的 expected_updated_at 从此处读取）
                    "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        },
        ensure_ascii=False,
    )


class RenameMediaArgs(BaseModel):
    """重命名媒体（显示名；不动存储对象）。expected_updated_at 为读取时的 updated_at。"""

    media_id: int
    new_name: str = Field(min_length=1, max_length=255)
    expected_updated_at: str = Field(min_length=10, description="读取媒体时拿到的 updatedAt（乐观比对）")


class TagMediaArgs(BaseModel):
    """追加媒体标签（追加去重，不覆盖既有标签）。"""

    media_id: int
    tags: list[str] = Field(min_length=1, max_length=10)
    expected_updated_at: str = Field(min_length=10, description="读取媒体时拿到的 updatedAt（乐观比对）")


def _load_owned_media(ctx: Any, media_id: int) -> tuple[MediaAsset | None, str | None]:
    row = ctx.db.get(MediaAsset, media_id)
    if row is None or row.delete_time is not None:
        return None, f"未找到媒体资产（media:{media_id}）"
    if row.created_by not in (None, ctx.user_id) and not ctx.is_super_admin:
        return None, "仅媒体属主可修改该资产"
    return row, None


def _check_optimistic_lock(row: MediaAsset, expected_updated_at: str) -> str | None:
    """E3 乐观比对：expected 与当前 updated_at 不一致 = 目标已被他人修改，拒绝写入。"""
    try:
        expected = datetime.fromisoformat(expected_updated_at.replace("Z", "+00:00"))
    except ValueError:
        return "expected_updated_at 格式非法（须为 ISO 时间）"
    current = row.updated_at
    if current is None:
        return None  # 无锚点可比（历史行），放行由业务语义兜底
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if expected.timestamp() != current.timestamp():
        return f"媒体已被其他人修改（读取时 {expected.isoformat()}，当前 {current.isoformat()}），请重新读取后再试"
    return None


def rename_media(args: RenameMediaArgs, ctx: Any) -> str:
    """重命名媒体显示名：属主限定 + 乐观比对（不覆盖他人修改）。

    写后显式刷新 updated_at（BaseEntity 无 onupdate）——agent 写路径的乐观锚点真实滚动；
    管理页 update 链暂不刷新（边界：管理页写不被既有锚点感知，见设计 R1 跟进）。
    """
    row, error = _load_owned_media(ctx, args.media_id)
    if error is not None:
        return json.dumps({"renamed": False, "error": error}, ensure_ascii=False)
    lock_error = _check_optimistic_lock(row, args.expected_updated_at)
    if lock_error is not None:
        return json.dumps({"renamed": False, "error": lock_error}, ensure_ascii=False)
    old_name = row.file_name
    row.file_name = args.new_name
    row.updated_at = datetime.now(UTC)
    ctx.db.add(row)
    ctx.db.commit()
    ctx.audit_target_ref = f"media:{row.id}"  # E3 审计：写操作目标引用
    return json.dumps({"renamed": True, "id": row.id, "from": old_name, "to": row.file_name}, ensure_ascii=False)


def tag_media(args: TagMediaArgs, ctx: Any) -> str:
    """追加媒体标签：读旧 JSON 数组（空/坏值归 []）→ 追加去重 → 写回；不覆盖既有标签。"""
    row, error = _load_owned_media(ctx, args.media_id)
    if error is not None:
        return json.dumps({"tagged": False, "error": error}, ensure_ascii=False)
    lock_error = _check_optimistic_lock(row, args.expected_updated_at)
    if lock_error is not None:
        return json.dumps({"tagged": False, "error": lock_error}, ensure_ascii=False)
    try:
        existing = json.loads(row.tags or "[]")
        if not isinstance(existing, list):
            existing = []
    except ValueError:
        existing = []
    cleaned = [t.strip()[:_MAX_TAG_LEN] for t in args.tags if t.strip()]
    merged = list(dict.fromkeys([*existing, *cleaned]))[:_MAX_TAGS]
    row.tags = json.dumps(merged, ensure_ascii=False)
    row.updated_at = datetime.now(UTC)  # 乐观锚点滚动（同 rename_media 注记）
    ctx.db.add(row)
    ctx.db.commit()
    ctx.audit_target_ref = f"media:{row.id}"
    return json.dumps({"tagged": True, "id": row.id, "tags": merged}, ensure_ascii=False)


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "search_media",
            "description": "按关键词搜索媒体库（文件名/生成提示词），返回媒体资产元信息列表",
            "level": "readonly",
            "args_model": SearchMediaArgs,
            "func": search_media,
        },
        {
            "name": "rename_media",
            "description": "重命名媒体资产的显示文件名（需提供读取时的 updatedAt 做并发校验；仅属主可操作）",
            "level": "reversible_write",
            "args_model": RenameMediaArgs,
            "func": rename_media,
            "safety": {
                "reversible_how": "显示名可再次重命名回退；不触碰存储对象与生成产物",
                "concurrency": "expected_updated_at 乐观比对——目标被他人修改后拒绝写入（不静默覆盖）",
                "audit_ref": "返回并记录 media:{id}",
            },
        },
        {
            "name": "tag_media",
            "description": "为媒体资产追加标签（追加去重，不覆盖既有标签；需 updatedAt 并发校验；仅属主可操作）",
            "level": "reversible_write",
            "args_model": TagMediaArgs,
            "func": tag_media,
            "safety": {
                "reversible_how": "追加语义，标签可在管理页移除；不覆盖既有标签集合",
                "concurrency": "expected_updated_at 乐观比对——目标被他人修改后拒绝写入",
                "audit_ref": "返回并记录 media:{id}",
            },
        },
    ]
