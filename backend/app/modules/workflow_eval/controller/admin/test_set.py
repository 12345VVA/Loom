"""工作流评估测试集管理 API。"""

from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
)
from app.framework.router.route_meta import Post
from app.modules.base.model.auth import User
from app.modules.base.service.security_service import get_current_user
from app.modules.workflow_eval.model.test_set import (
    WorkflowTestCaseImportRequest,
    WorkflowTestSetCreateRequest,
    WorkflowTestSetRead,
    WorkflowTestSetUpdateRequest,
)
from app.modules.workflow_eval.service.test_set_service import WorkflowTestSetService


@CoolController(
    CoolControllerMeta(
        module="workflow_eval",
        resource="test_set",
        scope="admin",
        service=WorkflowTestSetService,
        tags=("workflow_eval", "test_set"),
        code_prefix="workflow_eval_test_set",
        list_response_model=WorkflowTestSetRead,
        page_item_model=WorkflowTestSetRead,
        info_response_model=WorkflowTestSetRead,
        add_request_model=WorkflowTestSetCreateRequest,
        add_response_model=WorkflowTestSetRead,
        update_request_model=WorkflowTestSetUpdateRequest,
        update_response_model=WorkflowTestSetRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("name", "description"),
            field_eq=("definition_id",),
            order_fields=("created_at", "name"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowTestSetController(BaseController):
    @Post("/importCases", summary="批量导入测试用例", permission="workflow_eval:test_set:importCases")
    def import_cases(
        self,
        payload: WorkflowTestCaseImportRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        cases = [c.model_dump() for c in payload.cases]
        return WorkflowTestSetService(session).import_cases(payload.test_set_id, cases)


router = WorkflowTestSetController.router
