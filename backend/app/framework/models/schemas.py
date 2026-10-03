"""框架级通用 schema（自 base/model/auth.py 下沉，依赖方向正转）。

纯 pydantic 定义、零业务耦合；base 侧保留 re-export 兼容既有引用。
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel
from pydantic import Field as PydanticField

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    """分页响应"""

    items: list[T]
    total: int
    page: int
    page_size: int


class DeleteRequest(BaseModel):
    """批量删除请求"""

    ids: list[int] = PydanticField(default_factory=list)
