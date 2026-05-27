"""
工作流 Celery 异步任务入口。
将工作流执行从 Web 进程剥离到独立 Worker，避免进程重启丢失运行中实例。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.celery_app import celery_app
from app.core.database import Session, engine
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.service.checkpointer import get_checkpointer
from app.modules.workflow.service.compiler import WorkflowCompiler
from app.modules.workflow.service.event_bus import publish_event
import app.modules.workflow.service.workflow_service

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workflow.execute",
    bind=True,
    max_retries=0,
    task_time_limit=30 * 60,
)
def execute_workflow(self, instance_id: int, definition_id: int, initial_vars_json: str, resume_val_json: str = None):
    """
    在 Celery Worker 中执行或恢复一个工作流实例。
    """
    initial_vars = json.loads(initial_vars_json)
    resume_val = json.loads(resume_val_json) if resume_val_json else None
    asyncio.run(_async_execute(instance_id, definition_id, initial_vars, resume_val))


async def _async_execute(
    instance_id: int,
    definition_id: int,
    initial_vars: dict,
    resume_val: Any = None,
):
    """异步工作流执行体，逻辑与 WorkflowInstanceService._run_workflow 对齐。"""
    from langgraph.types import Command

    try:
        # 1. 编译拓扑
        with Session(engine) as session:
            instance = session.get(WorkflowInstance, instance_id)
            definition = session.get(WorkflowDefinition, definition_id)
            if not instance or not definition:
                logger.error("工作流执行失败: 找不到实例 %d 或定义 %d", instance_id, definition_id)
                return
            thread_id = instance.thread_id
            graph_json_str = definition.graph_json

        graph_json = json.loads(graph_json_str)
        logger.info(
            "[Workflow] Compiling graph: instance=%d, nodes=%s, edges=%s",
            instance_id,
            [n.get("id") for n in graph_json.get("nodes", [])],
            [(e.get("source"), e.get("target"), e.get("type")) for e in graph_json.get("edges", [])],
        )
        graph = WorkflowCompiler.compile_graph(graph_json)
        compiled = graph.compile(checkpointer=get_checkpointer())
        logger.info("[Workflow] Graph compiled successfully, instance=%d", instance_id)

        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}

        # 2. 区分启动与恢复
        if resume_val is not None:
            events = compiled.astream(
                Command(resume=resume_val), config=config, stream_mode="updates"
            )
        else:
            initial_state = {"messages": [], "variables": initial_vars, "current_node": "start"}
            events = compiled.astream(initial_state, config=config, stream_mode="updates")

        last_step_time = time.perf_counter()
        current_vars = initial_vars
        event_count = 0

        # 预先构建节点字典映射，避免在事件循环中进行 O(N) 线性查找性能损耗
        nodes_map = {node["id"]: node for node in graph_json.get("nodes", [])}

        # 3. 迭代执行事件
        async for event in events:
            for node_id, node_output in event.items():
                event_count += 1
                current_time = time.perf_counter()
                latency_ms = int((current_time - last_step_time) * 1000)
                last_step_time = current_time

                if node_id == "__interrupt__":
                    with Session(engine) as session:
                        instance = session.get(WorkflowInstance, instance_id)
                        if instance:
                            instance.status = "paused"
                            instance.current_node = instance.current_node or "human_input"
                            session.add(instance)
                            session.commit()
                            current_node_name = instance.current_node
                        else:
                            current_node_name = "human_input"

                    publish_event(instance_id, "paused", {
                        "node_id": current_node_name,
                        "status": "paused",
                    })
                    return

                new_vars = node_output.get("variables", {})
                logger.info(
                    "[Workflow] Event #%d: node=%s, vars_keys=%s, instance=%d",
                    event_count, node_id, list(new_vars.keys()) if isinstance(new_vars, dict) else None, instance_id,
                )

                with Session(engine) as session:
                    instance = session.get(WorkflowInstance, instance_id)
                    if instance:
                        instance.current_node = node_id
                        instance.state_data = json.dumps(new_vars)
                        session.add(instance)

                    node_info = nodes_map.get(node_id, {})
                    exec_log = WorkflowExecutionLog(
                        instance_id=instance_id,
                        node_id=node_id,
                        node_name=node_info.get("name") or node_id,
                        node_type=node_info.get("type") or "unknown",
                        input_data=json.dumps(current_vars),
                        output_data=json.dumps(new_vars),
                        latency_ms=latency_ms,
                        status="success",
                    )
                    session.add(exec_log)
                    session.commit()

                current_vars = new_vars

                publish_event(instance_id, "node_update", {
                    "node_id": node_id,
                    "variables": new_vars,
                    "status": "running",
                })

        # 执行完毕
        logger.info("[Workflow] Execution completed: instance=%d, total_events=%d", instance_id, event_count)
        with Session(engine) as session:
            instance = session.get(WorkflowInstance, instance_id)
            state_data_str = "{}"
            if instance:
                instance.status = "success"
                session.add(instance)
                session.commit()
                state_data_str = instance.state_data

        final_vars = json.loads(state_data_str)
        workflow_output = final_vars.pop("workflow_output", None)
        publish_event(instance_id, "success", {
            "status": "success",
            "variables": final_vars,
            "output": workflow_output,
        })

    except Exception as e:
        logger.error("工作流运行异常: %s", e, exc_info=True)
        try:
            with Session(engine) as session:
                instance = session.get(WorkflowInstance, instance_id)
                if instance:
                    instance.status = "failed"
                    instance.error_message = str(e)
                    session.add(instance)
                    session.commit()
        except Exception as se:
            logger.error("记录工作流异常失败: %s", se, exc_info=True)

        publish_event(instance_id, "failed", {"status": "failed", "error": str(e)})


def _get_node_name(graph_json: dict, node_id: str) -> str:
    nodes_map = {node["id"]: node for node in graph_json.get("nodes", [])}
    return nodes_map.get(node_id, {}).get("name") or node_id


def _get_node_type(graph_json: dict, node_id: str) -> str:
    nodes_map = {node["id"]: node for node in graph_json.get("nodes", [])}
    return nodes_map.get(node_id, {}).get("type") or "unknown"
