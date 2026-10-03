"""
工作流动态编译器（门面 + 编译主体）。

实现按域拆分：
- expressions.py — SafeEvaluator/safe_eval 表达式求值、render_template 模板渲染、key 转换
- graph_validate.py — validate_graph 拓扑校验、子图体节点定位
- state.py — WorkflowState、NodeExecutorRegistry/node_registry、输入输出映射

本模块保留全部历史符号的 re-export，外部统一从本模块 import。
"""

import logging
from typing import Any

# GraphBubbleUp 自 langgraph 0.2.54 起才在 langgraph.errors 中定义（0.2.53 及更早无此类，
# 该版本以下此行为模块顶层硬导入，会导致整个 workflow 模块 ImportError）。下限见 requirements.txt。
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph

from app.modules.workflow.service.expressions import (  # noqa: F401
    SafeEvaluator as SafeEvaluator,
)
from app.modules.workflow.service.expressions import (  # noqa: F401
    _deep_get as _deep_get,
)
from app.modules.workflow.service.expressions import (
    convert_keys_to_snake,
    safe_eval,
)
from app.modules.workflow.service.expressions import (  # noqa: F401
    render_template as render_template,
)
from app.modules.workflow.service.expressions import (  # noqa: F401
    strip_braces as strip_braces,
)
from app.modules.workflow.service.graph_validate import (  # noqa: F401
    CONDITIONAL_NODE_TYPES as CONDITIONAL_NODE_TYPES,
)
from app.modules.workflow.service.graph_validate import (  # noqa: F401
    SUBGRAPH_NODE_TYPES as SUBGRAPH_NODE_TYPES,
)
from app.modules.workflow.service.graph_validate import (  # noqa: F401
    UNTESTABLE_NODE_TYPES as UNTESTABLE_NODE_TYPES,
)
from app.modules.workflow.service.graph_validate import (
    _build_group_to_controller_map,
    _find_body_nodes_by_parent,
)
from app.modules.workflow.service.graph_validate import (  # noqa: F401
    _find_body_nodes as _find_body_nodes,
)
from app.modules.workflow.service.graph_validate import (  # noqa: F401
    validate_graph as validate_graph,
)
from app.modules.workflow.service.state import (  # noqa: F401
    NodeExecutorRegistry as NodeExecutorRegistry,
)
from app.modules.workflow.service.state import (  # noqa: F401
    WorkflowState as WorkflowState,
)
from app.modules.workflow.service.state import (  # noqa: F401
    apply_input_mappings as apply_input_mappings,
)
from app.modules.workflow.service.state import (
    apply_output_mappings,
    resolve_node_inputs,
)
from app.modules.workflow.service.state import (  # noqa: F401
    node_registry as node_registry,
)

logger = logging.getLogger(__name__)


class NodeExecutionError(Exception):
    """节点执行失败（重试耗尽后抛出），携带 node_id 供上层记录 failed_node_id。"""

    def __init__(self, node_id: str, attempts: int, cause: Exception):
        self.node_id = node_id
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"节点 '{node_id}' 执行失败（已尝试 {attempts} 次）: {cause}")


def _extract_body_edges(body_node_ids: set[str], parent_id: str, edges: list) -> list[dict]:
    """提取体子图的内部边和回边（回边 target == parent 会编译时重定向为 → END）。"""
    body_edges = []
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        # 内部边：source 和 target 都在体节点中
        if source in body_node_ids and target in body_node_ids:
            body_edges.append(edge)
        # 回边：体节点连回父节点
        elif source in body_node_ids and target == parent_id:
            body_edges.append(edge)
    return body_edges


def _validate_subgraph_boundaries(parent_id: str, body_node_ids: set[str], edges: list, nodes_map: dict) -> None:
    """校验体子图边界：无越界逃逸、无外部入边。"""
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        # 体节点向外的越界边：只允许连回父节点或体内部
        if source in body_node_ids:
            if target != parent_id and target not in body_node_ids:
                src_name = nodes_map.get(source, {}).get("name", source)
                tgt_name = nodes_map.get(target, {}).get("name", target)
                raise ValueError(
                    f"循环体节点 '{src_name}' 的连线越界：直接连向了循环外的节点 '{tgt_name}'。"
                    f"循环体内节点只能连回循环控制节点或体内部节点。"
                )
        # 外部节点向体内部入边：只允许父节点连向体入口
        if target in body_node_ids and source != parent_id:
            src_name = nodes_map.get(source, {}).get("name", source)
            tgt_name = nodes_map.get(target, {}).get("name", target)
            raise ValueError(
                f"循环外节点 '{src_name}' 直接连向了循环体内的节点 '{tgt_name}'。"
                f"循环体外节点不能直接连入体内部，只能通过循环控制节点进入。"
            )


def _add_conditional_edges_for_node(builder, node: dict, edges: list | None = None) -> None:
    """为单个条件节点注册 conditional edges，供主图和体子图复用。"""
    node_id = node["id"]
    node_type = node["type"]
    node_config = convert_keys_to_snake(node.get("config", {}))

    if node_type == "condition":
        true_route = node_config.get("true_route")
        false_route = node_config.get("false_route")
        # 回退：从边的 sourceHandle 推导路由
        if (not true_route or not false_route) and edges:
            for e in edges:
                if e.get("source") != node_id:
                    continue
                sh = e.get("source_handle") or e.get("sourceHandle")
                if sh == "true" and not true_route:
                    true_route = e["target"]
                elif sh == "false" and not false_route:
                    false_route = e["target"]
        path_map = {END: END}
        if true_route:
            path_map[true_route] = true_route
        if false_route:
            path_map[false_route] = false_route
        if len(path_map) > 1:
            builder.add_conditional_edges(
                node_id, WorkflowCompiler.create_conditional_router(node_id, node_config), path_map
            )

    elif node_type == "intent_classifier":
        intents = list(node_config.get("intents", []))
        default_route = node_config.get("default_route")
        # 从边的 sourceHandle 推导路由
        if edges:
            for e in edges:
                if e.get("source") != node_id:
                    continue
                sh = e.get("source_handle") or e.get("sourceHandle")
                if sh == "default" and not default_route:
                    default_route = e["target"]
                elif sh and sh.startswith("intent_"):
                    rest = sh[len("intent_") :]
                    match = next((x for x in intents if str(x.get("id")) == rest), None)
                    if match is not None:
                        match["target_route"] = e["target"]
                    elif rest.isdigit() and int(rest) < len(intents):
                        intents[int(rest)]["target_route"] = e["target"]
        path_map = {}
        for intent in intents:
            target = intent.get("target_route")
            if target:
                path_map[target] = target
        if default_route:
            node_config["default_route"] = default_route
            path_map[default_route] = default_route
        path_map[END] = END
        if path_map:
            builder.add_conditional_edges(
                node_id, WorkflowCompiler.create_intent_router(node_id, node_config), path_map
            )

    elif node_type == "switch":
        cases = list(node_config.get("cases", []))
        default_route = node_config.get("default_route")
        # 从边的 sourceHandle 推导路由
        if edges:
            for e in edges:
                if e.get("source") != node_id:
                    continue
                sh = e.get("source_handle") or e.get("sourceHandle")
                if sh == "default" and not default_route:
                    default_route = e["target"]
                elif sh and sh.startswith("case_"):
                    rest = sh[len("case_") :]
                    match = next((x for x in cases if str(x.get("id")) == rest), None)
                    if match is not None:
                        match["target_route"] = e["target"]
                    elif rest.isdigit() and int(rest) < len(cases):
                        cases[int(rest)]["target_route"] = e["target"]
        path_map = {}
        for case in cases:
            target = case.get("target_route")
            if target:
                path_map[target] = target
        if default_route:
            node_config["default_route"] = default_route
            path_map[default_route] = default_route
        path_map[END] = END
        if path_map:
            builder.add_conditional_edges(
                node_id, WorkflowCompiler.create_switch_router(node_id, node_config), path_map
            )


def _compile_body_graph(body_nodes: list, body_edges: list, body_entry_id: str, parent_id: str):
    """将体节点编译为独立的 LangGraph StateGraph（无 checkpointer，瞬态执行）。"""
    builder = StateGraph(WorkflowState)

    # 注册体节点（复用 create_node_runner）
    for node in body_nodes:
        node_id = node["id"]
        node_type = node["type"]
        node_config = convert_keys_to_snake(node.get("config", {}))
        builder.add_node(node_id, WorkflowCompiler.create_node_runner(node_id, node_type, node_config))

    # START → 体入口
    builder.add_edge(START, body_entry_id)

    # 体内部边 + 条件节点处理
    # 先收集条件节点，后续统一处理
    body_condition_nodes = []
    for edge in body_edges:
        source = edge["source"]
        target = edge["target"]

        if target == parent_id:
            # 回边 → END
            builder.add_edge(source, END)
            continue

        # 检查 source 是否是条件节点（需要 add_conditional_edges 而非 add_edge）
        source_node = next((n for n in body_nodes if n["id"] == source), None)
        if source_node and source_node["type"] in CONDITIONAL_NODE_TYPES:
            body_condition_nodes.append(source_node)
            continue

        builder.add_edge(source, target)

    # 处理体内部的条件节点（复用共享注册函数）
    for cond_node in body_condition_nodes:
        _add_conditional_edges_for_node(builder, cond_node, body_edges)
    for node in body_nodes:
        if node["type"] == "end":
            builder.add_edge(node["id"], END)

    logger.info("[Compiler] Body sub-graph compiled: entry=%s, nodes=%s", body_entry_id, [n["id"] for n in body_nodes])
    return builder.compile()


def _compile_subgraphs_recursive(graph_json: dict, nodes_map: dict) -> tuple[dict, set[str]]:
    """
    递归预处理所有子图节点：由内而外编译体子图。
    返回 (subgraph_configs, all_body_node_ids)。
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])
    subgraph_configs = {}
    all_body_node_ids = set()

    # 找到所有子图节点
    sg_nodes = [n for n in nodes if n.get("type") in SUBGRAPH_NODE_TYPES]

    # 递归编译（由内而外）
    def _process(sg_node):
        sg_id = sg_node["id"]
        if sg_id in subgraph_configs:
            return  # 已处理

        config = convert_keys_to_snake(sg_node.get("config", {}))

        # 优先尝试 parentNode（group 容器）模式
        parent_result = _find_body_nodes_by_parent(nodes, edges, sg_id)
        if parent_result[0]:
            body_node_ids = parent_result[0]
            body_entry = parent_result[1]
        else:
            # 回退到 BFS 模式（旧工作流）
            body_entry = config.get("loop_body_route")
            if not body_entry:
                return
            body_node_ids = _find_body_nodes(sg_id, body_entry, edges)

        if not body_node_ids:
            return

        # 若体节点中包含另一个子图节点，先递归处理内层
        for nid in body_node_ids:
            inner_node = nodes_map.get(nid)
            if inner_node and inner_node.get("type") in SUBGRAPH_NODE_TYPES:
                _process(inner_node)

        # 校验体边界
        _validate_subgraph_boundaries(sg_id, body_node_ids, edges, nodes_map)

        # 提取体边
        body_edges = _extract_body_edges(body_node_ids, sg_id, edges)

        # 编译体子图
        body_nodes_list = [nodes_map[nid] for nid in body_node_ids if nid in nodes_map]
        compiled_body = _compile_body_graph(body_nodes_list, body_edges, body_entry, sg_id)

        subgraph_configs[sg_id] = {
            "compiled_body": compiled_body,
            "body_node_ids": body_node_ids,
            "config": config,
        }
        all_body_node_ids.update(body_node_ids)

    for sg_node in sg_nodes:
        _process(sg_node)

    logger.info(
        "[Compiler] Pre-pass complete: %d subgraph(s) extracted, body_nodes=%s",
        len(subgraph_configs),
        all_body_node_ids,
    )
    return subgraph_configs, all_body_node_ids


# --- 3. 动态图编译器 ---
class WorkflowCompiler:
    """
    工作流拓扑 JSON 编译器，负责实例化为 LangGraph 的 StateGraph
    """

    @classmethod
    def compile_graph(cls, graph_json: dict[str, Any]) -> StateGraph:
        """
        根据前端配置的拓扑 JSON 编译成 LangGraph 图。
        支持 for_each / batch 子图：循环体在 Pre-pass 阶段提取为独立子图，
        主图保持纯 DAG 结构。
        """
        # 确保节点执行器已注册：注册逻辑位于 workflow_service 模块体（与 compiler 分离）。
        # 此处延迟导入可打破循环依赖（compiler 顶层不 import workflow_service），
        # 使任何调用 compile_graph 的入口（Celery / 测试脚本 / 未来新入口）都能自动完成注册，
        # 无需各自记得 import workflow_service。
        import app.modules.workflow.service.workflow_service  # noqa: F401

        # 0. 校验拓扑数据结构与完整性
        if not isinstance(graph_json, dict) or "nodes" not in graph_json or "edges" not in graph_json:
            raise ValueError("工作流拓扑结构不合法，必须包含 nodes 和 edges 字段。")

        # 严格验证图结构完整性
        validate_graph(graph_json)

        # 获取所有节点和边定义
        nodes = graph_json.get("nodes", [])
        edges = graph_json.get("edges", [])
        nodes_map = {n["id"]: n for n in nodes}

        # === Pre-pass: 提取并编译所有子图 ===
        subgraph_configs, all_body_node_ids = _compile_subgraphs_recursive(graph_json, nodes_map)

        # 创建主图
        builder = StateGraph(WorkflowState)

        # 1. 遍历注册所有工作节点（跳过体节点和 group 容器）
        for node in nodes:
            node_id = node["id"]
            node_type = node["type"]
            node_config = convert_keys_to_snake(node.get("config", {}))

            # 跳过开始辅助节点
            if node_type == "start":
                continue

            # 跳过 loop_body_group 容器节点（纯视觉分组，不参与执行）
            if node_type == "loop_body_group":
                continue

            # 跳过子图体节点（它们已被编译到各自的子图中）
            if node_id in all_body_node_ids:
                continue

            # 对子图执行节点，注入已编译的体子图
            if node_id in subgraph_configs:
                node_config["_compiled_body"] = subgraph_configs[node_id]["compiled_body"]

            builder.add_node(node_id, cls.create_node_runner(node_id, node_type, node_config))

        # 2. 遍历并建立连线关系
        added_edges = []
        skipped_edges = []

        group_to_controller = _build_group_to_controller_map(nodes, edges, nodes_map)

        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            edge_type = edge.get("type", "direct")

            source_node = nodes_map.get(source)
            target_node = nodes_map.get(target)

            source_type = source_node.get("type") if source_node else None
            target_type = target_node.get("type") if target_node else None

            # 处理 loop_body_group 相关的边：短路（shortcut）而非丢弃
            if source_type == "loop_body_group" or target_type == "loop_body_group":
                # group → X：短路为 controller → X
                if source_type == "loop_body_group" and source in group_to_controller:
                    real_source = group_to_controller[source]
                    if target not in all_body_node_ids and target != real_source and target_type != "loop_body_group":
                        logger.info(f"[Compiler] Edge shortcut: {real_source} → {target} (via group {source})")
                        builder.add_edge(real_source, target)
                        added_edges.append(f"{real_source} → {target} (shortcut via {source})")
                # target == group（如 controller → group）或无映射：跳过
                skipped_edges.append(f"{source} → {target} (group)")
                continue

            # 跳过体节点内部的边（已编译进子图）
            if source in all_body_node_ids or target in all_body_node_ids:
                # 但 target == 子图父节点（回边）的情况也要跳过
                skipped_edges.append(f"{source} → {target} (body)")
                continue

            # 从 START 连接
            if source_type == "start":
                logger.info(f"[Compiler] Edge: START → {target}")
                builder.add_edge(START, target)
                added_edges.append(f"START → {target}")
                continue

            # 连接到结束节点
            if target_type == "end":
                logger.info(f"[Compiler] Edge: {source} → {target} (to-end)")
                builder.add_edge(source, target)
                added_edges.append(f"{source} → {target}")
                continue

            # 条件分流节点的出边由步骤 3 处理
            if source_type in CONDITIONAL_NODE_TYPES:
                logger.info(f"[Compiler] Edge deferred to conditional routing: {source}({source_type}) → {target}")
                skipped_edges.append(f"{source} → {target} (conditional)")
                continue

            # 所有其他节点的出边一律添加
            logger.info(f"[Compiler] Edge: {source}({source_type}) → {target} (edge_visual_type={edge_type})")
            builder.add_edge(source, target)
            added_edges.append(f"{source} → {target}")

        logger.info(
            f"[Compiler] Graph edges summary: added={len(added_edges)}, skipped={len(skipped_edges)} | {added_edges}"
        )

        # 2.5 结束节点统一连向 END
        for node in nodes:
            if node.get("type") == "end" and node["id"] not in all_body_node_ids:
                builder.add_edge(node["id"], END)

        # 3. 遍历并处理条件边与分流节点
        for node in nodes:
            node_id = node["id"]
            node_type = node["type"]
            # 跳过体节点中的条件节点（已编译进子图）
            if node_id in all_body_node_ids:
                continue
            node_config = convert_keys_to_snake(node.get("config", {}))

            if node_type in CONDITIONAL_NODE_TYPES:
                _add_conditional_edges_for_node(builder, node, edges)

        logger.info("[Compiler] Graph build complete: nodes=%s", list(builder.nodes.keys()))

        return builder

    @classmethod
    def create_node_runner(cls, node_id: str, node_type: str, config: dict[str, Any]):
        """
        生成一个满足 LangGraph 要求的节点运行函数
        """

        async def node_runner(state: WorkflowState) -> dict[str, Any]:
            import asyncio

            from app.core.config import settings

            # 记录当前执行节点
            state["current_node"] = node_id

            # 获取对应的注册执行器
            executor = node_registry.get(node_type)
            if not executor:
                raise ValueError(f"工作流中使用了未注册的节点类型: '{node_type}'")

            # 1. 应用输入变量映射，提炼入参
            node_inputs = resolve_node_inputs(state["variables"], config)

            # 2. 运行执行器（节点级自动重试：全局默认 + 节点 config 覆盖；指数退避）
            #    重试在 node_runner 内部，updates 在 return 后才 apply 到 state，故前次失败不污染 state
            executor_config = {**config, "id": node_id}
            max_attempts = config.get("retry_max_attempts")
            if max_attempts is None:
                max_attempts = settings.WORKFLOW_NODE_RETRY_MAX_ATTEMPTS
            max_attempts = max(1, int(max_attempts))  # 至少尝试 1 次
            backoff_base = config.get("retry_backoff_base")
            if backoff_base is None:
                backoff_base = settings.WORKFLOW_NODE_RETRY_BACKOFF_BASE

            updates = None
            for attempt in range(1, max_attempts + 1):
                try:
                    updates = await executor(node_inputs, executor_config)
                    break
                except GraphBubbleUp:
                    # 控制流信号：interrupt 中断（人工审批挂起）/ drain 优雅停机。
                    # 必须原样冒泡给 LangGraph —— 既不重试，也不包装为 NodeExecutionError，
                    # 否则 human_input 永远无法进入 paused，停机信号也会被误判为节点失败。
                    raise
                except Exception as e:
                    if attempt >= max_attempts:
                        # 重试耗尽：抛 NodeExecutionError 携带 node_id，供上层写 failed_node_id
                        raise NodeExecutionError(node_id, attempt, e) from e
                    delay = float(backoff_base) * (2 ** (attempt - 1))
                    logger.warning(
                        "节点 '%s' 第 %d/%d 次执行失败，%.1fs 后重试: %s",
                        node_id,
                        attempt,
                        max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
            if updates is None:
                updates = {}

            # 3. 应用输出变量映射，写回全局状态
            output_mappings = config.get("output_mappings", {})
            new_variables = apply_output_mappings(state["variables"], updates, output_mappings)

            return {"variables": new_variables, "current_node": node_id}

        return node_runner

    @classmethod
    def create_conditional_router(cls, node_id: str, config: dict[str, Any]):
        """
        生成条件边的动态路由逻辑
        """

        def conditional_router(state: WorkflowState) -> str:
            expression = config.get("expression", "True")
            true_route = config.get("true_route")
            false_route = config.get("false_route")

            # 安全的评估上下文
            eval_context = {
                **state.get("variables", {}),
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
            }

            try:
                # 使用自定义安全 AST 语法树评估器，杜绝代码注入漏洞
                result = safe_eval(expression, eval_context)
                return true_route if result else (false_route or END)
            except Exception as e:
                # 求值失败仍按既有语义回落 false 路由，但日志必须能定位到具体节点：
                # 否则用户只会看到「分支莫名走错」，排查成本极高
                logger.error(
                    "[Workflow Router Error] 节点 '%s' 条件表达式 '%s' 求值失败，已回落 false 路由: %s",
                    node_id,
                    expression,
                    e,
                )
                return false_route or END

        return conditional_router

    @classmethod
    def create_intent_router(cls, node_id: str, config: dict[str, Any]):
        """
        生成意图分类分支路由逻辑
        """

        def intent_router(state: WorkflowState) -> str:
            target_route = state.get("variables", {}).get(f"{node_id}_selected_route")
            return target_route or config.get("default_route") or END

        return intent_router

    @classmethod
    def create_switch_router(cls, node_id: str, config: dict[str, Any]):
        """
        生成 Switch-Case 多路分支的动态路由逻辑
        """

        def switch_router(state: WorkflowState) -> str:
            var_name = strip_braces(config.get("variable", ""))
            val = state.get("variables", {})
            if var_name.startswith("variables."):
                var_key = var_name.removeprefix("variables.")
                val = val.get(var_key)
            else:
                val = val.get(var_name)

            for case in config.get("cases", []):
                if str(case.get("value")) == str(val):
                    return case.get("target_route") or END
            return config.get("default_route") or END

        return switch_router
