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


class SampleProductionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    definition_id: int
    test_set_id: int
    limit: int = 50
    days: int = 7


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

    @Get("/poll", summary="轮询评估运行结果（CI 门禁用）", permission="workflow_eval:eval_run:page")
    def poll(
        self,
        eval_run_id: int = Query(..., alias="evalRunId"),
        timeout: int = Query(3600, ge=1, le=7200, description="最长等待秒数"),
        interval: int = Query(5, ge=1, le=30, description="轮询间隔秒数"),
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """轮询直到终态或超时，返回终态 + 指标。CI 门禁：start → poll → 判 pass_rate/verdict。"""
        return WorkflowEvalRunService(session).poll(eval_run_id, timeout, interval)

    @Post(
        "/sampleProduction",
        summary="采样生产实例入黄金集（在线评测）",
        permission="workflow_eval:eval_run:start",
    )
    def sample_production(
        self,
        payload: SampleProductionRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """采样 success 实例的 input/output（脱敏）入黄金测试集，回放监控生产质量漂移。"""
        return WorkflowEvalRunService(session).sample_production(
            payload.definition_id, payload.test_set_id, payload.limit, payload.days
        )


router = WorkflowEvalRunController.router
