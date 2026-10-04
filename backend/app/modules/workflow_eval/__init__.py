"""工作流评价系统模块入口。

载荷引用保护注册（H4 解耦）：eval case 结果的大输出（actual_output）offload 在
workflow 统一的载荷文件（wf_payload_*）中，workflow 的每日孤儿清扫必须感知这些
存活引用才不会误删文件。在包导入时向 workflow.cleanup_service 注册收集器，
依赖方向保持 eval→workflow 单向；包级注册保证 API（loader 导入控制器）、
Celery worker（include 导入 eval_tasks）、测试（导入模型）任一进程均生效。
"""


def _register_payload_ref_protection() -> None:
    from sqlmodel import select

    from app.modules.workflow.service.cleanup_service import PAYLOAD_REF_PROVIDERS
    from app.modules.workflow_eval.model.eval_run import WorkflowEvalCaseResult

    def _eval_payload_refs(session) -> list[str | None]:
        return list(
            session.exec(
                select(WorkflowEvalCaseResult.actual_output_storage_ref).where(
                    WorkflowEvalCaseResult.delete_time == None,  # noqa: E711
                    WorkflowEvalCaseResult.actual_output_storage_ref != None,  # noqa: E711
                )
            ).all()
        )

    if _eval_payload_refs not in PAYLOAD_REF_PROVIDERS:
        PAYLOAD_REF_PROVIDERS.append(_eval_payload_refs)


_register_payload_ref_protection()
