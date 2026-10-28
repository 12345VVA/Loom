"""workflow 模块的智能体工具（首版封闭清单 D11）。

结构契约见 app/modules/agent/service/agent_tools.py 模块 docstring——本模块**零 import agent**，
ctx 为鸭子类型。仅列出已发布（有线上版本指针）且启用的流程定义，不含图结构细节。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.modules.workflow.model.workflow import WorkflowDefinition


class ListWorkflowDefinitionsArgs(BaseModel):
    """列出工作流定义。"""

    keyword: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


def list_workflow_definitions(args: ListWorkflowDefinitionsArgs, ctx: Any) -> str:
    """列出已发布且启用的工作流定义（名称/描述/当前版本号），不含图结构。"""
    session: Session = ctx.db
    statement = select(WorkflowDefinition).where(
        WorkflowDefinition.current_version_id != None,  # noqa: E711 —— 已发布（有线上版本指针）
        WorkflowDefinition.is_active == True,  # noqa: E712 —— 启用（停用定义不进清单）
        WorkflowDefinition.delete_time == None,  # noqa: E711
    )
    if args.keyword:
        like = f"%{args.keyword}%"
        statement = statement.where(
            (WorkflowDefinition.name.like(like)) | (WorkflowDefinition.description.like(like))  # type: ignore[attr-defined]
        )
    rows = session.exec(statement.limit(args.limit)).all()
    return json.dumps(
        {
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "code": row.code,
                    "name": row.name,
                    "description": row.description,
                    "currentVersionId": row.current_version_id,
                }
                for row in rows
            ],
        },
        ensure_ascii=False,
    )


def get_agent_tools() -> list[dict]:
    return [
        {
            "name": "list_workflow_definitions",
            "display_name": "工作流列表",
            "description": "列出系统中已发布且启用的工作流定义（名称/描述），供后续引用或答疑",
            "level": "readonly",
            "args_model": ListWorkflowDefinitionsArgs,
            "func": list_workflow_definitions,
        },
    ]
