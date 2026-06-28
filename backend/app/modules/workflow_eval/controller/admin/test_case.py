"""工作流评估测试用例管理 API（CRUD）。"""

from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
)
from app.modules.workflow_eval.model.test_set import (
    WorkflowTestCaseCreateRequest,
    WorkflowTestCaseRead,
    WorkflowTestCaseUpdateRequest,
)
from app.modules.workflow_eval.service.test_case_service import WorkflowTestCaseService


@CoolController(
    CoolControllerMeta(
        module="workflow_eval",
        resource="test_case",
        scope="admin",
        service=WorkflowTestCaseService,
        tags=("workflow_eval", "test_case"),
        code_prefix="workflow_eval_test_case",
        list_response_model=WorkflowTestCaseRead,
        page_item_model=WorkflowTestCaseRead,
        info_response_model=WorkflowTestCaseRead,
        add_request_model=WorkflowTestCaseCreateRequest,
        add_response_model=WorkflowTestCaseRead,
        update_request_model=WorkflowTestCaseUpdateRequest,
        update_response_model=WorkflowTestCaseRead,
        actions=("add", "delete", "update", "page", "info", "list"),
        page_query=QueryConfig(
            keyword_like_fields=("case_key",),
            field_eq=("test_set_id",),
            order_fields=("sort_order", "created_at", "case_key"),
            add_order_by=(OrderByConfig("sort_order", "asc"),),
        ),
        soft_delete=True,
    )
)
class WorkflowTestCaseController(BaseController):
    pass


router = WorkflowTestCaseController.router
