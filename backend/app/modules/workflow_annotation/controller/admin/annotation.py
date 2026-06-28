"""工作流评估人工标注 API：CRUD + Cohen's κ judge 校准。"""

from fastapi import Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
)
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow_annotation.model.annotation import (
    KappaRequest,
    WorkflowAnnotationCreateRequest,
    WorkflowAnnotationRead,
    WorkflowAnnotationUpdateRequest,
)
from app.modules.workflow_annotation.service.annotation_service import WorkflowAnnotationService


@CoolController(
    CoolControllerMeta(
        module="workflow_annotation",
        resource="annotation",
        scope="admin",
        service=WorkflowAnnotationService,
        tags=("workflow_annotation",),
        code_prefix="workflow_annotation",
        list_response_model=WorkflowAnnotationRead,
        page_item_model=WorkflowAnnotationRead,
        info_response_model=WorkflowAnnotationRead,
        add_request_model=WorkflowAnnotationCreateRequest,
        add_response_model=WorkflowAnnotationRead,
        update_request_model=WorkflowAnnotationUpdateRequest,
        update_response_model=WorkflowAnnotationRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            field_eq=(
                QueryFieldConfig(column="case_result_id", request_param="caseResultId"),
                QueryFieldConfig(column="annotator_user_id", request_param="annotatorUserId"),
                QueryFieldConfig(column="is_gold", request_param="isGold"),
            ),
            order_fields=("created_at",),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowAnnotationController(BaseController):
    @Post("/kappa", summary="计算 judge 与人工标注的 Cohen's κ", permission="workflow_annotation:annotation:kappa")
    def kappa(
        self,
        payload: KappaRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """计算评估运行的 judge 与人工标注 κ，回填 summary_payload.judge_calibration 并返回。"""
        if payload.eval_run_id <= 0:
            raise HTTPException(status_code=400, detail="缺少有效的 evalRunId")
        return WorkflowAnnotationService(session).compute_kappa(payload.eval_run_id)


router = WorkflowAnnotationController.router
