"""工作流评估运行 API：发起、查看用例结果、取消、回归对比。"""

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.core.database import get_session
from app.framework.api.naming import resolve_alias
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
)
from app.framework.router.route_meta import Get, Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow_eval.model.eval_run import (
    WorkflowEvalRunRead,
    WorkflowEvalRunStartRequest,
)
from app.modules.workflow_eval.service.eval_run_service import WorkflowEvalRunService


class WorkflowEvalRunCancelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    eval_run_id: int


@CoolController(
    CoolControllerMeta(
        module="workflow_eval",
        resource="eval_run",
        scope="admin",
        service=WorkflowEvalRunService,
        tags=("workflow_eval", "eval_run"),
        code_prefix="workflow_eval_run",
        list_response_model=WorkflowEvalRunRead,
        page_item_model=WorkflowEvalRunRead,
        info_response_model=WorkflowEvalRunRead,
        actions=("page", "info", "list", "delete"),
        page_query=QueryConfig(
            field_eq=("test_set_id", "definition_id", "status"),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowEvalRunController(BaseController):
    @Post("/start", summary="发起批量评估", permission="workflow_eval:eval_run:start")
    def start(
        self,
        payload: WorkflowEvalRunStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return WorkflowEvalRunService(session).start(payload, current_user)

    @Post("/cancel", summary="取消评估运行", permission="workflow_eval:eval_run:cancel")
    def cancel(
        self,
        payload: WorkflowEvalRunCancelRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        run = WorkflowEvalRunService(session).cancel(payload.eval_run_id, current_user)
        return run

    @Get("/cases", summary="查看评估用例结果", permission="workflow_eval:eval_run:cases")
    def list_cases(
        self,
        eval_run_id: int = Query(..., alias="evalRunId"),
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=200),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        return WorkflowEvalRunService(session).list_cases(eval_run_id, current_user, page, size)

    @Get("/compare", summary="两次评估的回归对比", permission="workflow_eval:eval_run:compare")
    def compare(
        self,
        run_a: int = Query(..., alias="runA"),
        run_b: int = Query(..., alias="runB"),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        from app.modules.workflow_eval.service.regression import compare_runs

        return compare_runs(session, run_a, run_b, current_user)


router = WorkflowEvalRunController.router
