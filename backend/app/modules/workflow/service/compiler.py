"""
工作流动态编译器与节点注册表。
"""

import ast
import collections
import json
import logging
import re
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

logger = logging.getLogger(__name__)
from langgraph.graph import END, START, StateGraph


class NodeExecutionError(Exception):
    """节点执行失败（重试耗尽后抛出），携带 node_id 供上层记录 failed_node_id。"""

    def __init__(self, node_id: str, attempts: int, cause: Exception):
        self.node_id = node_id
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"节点 '{node_id}' 执行失败（已尝试 {attempts} 次）: {cause}")


class SafeEvaluator:
    def __init__(self, context: dict):
        self.context = context
        self.allowed_calls = {"len": len, "str": str, "int": int, "float": float, "bool": bool}

    def evaluate(self, node: Any) -> Any:
        if isinstance(node, ast.Expression):
            return self.evaluate(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in self.context:
                return self.context[node.id]
            raise NameError(f"变量 '{node.id}' 未定义")
        elif isinstance(node, ast.Subscript):
            value = self.evaluate(node.value)
            if isinstance(node.slice, ast.Slice):
                lower = self.evaluate(node.slice.lower) if getattr(node.slice, "lower", None) is not None else None
                upper = self.evaluate(node.slice.upper) if getattr(node.slice, "upper", None) is not None else None
                step = self.evaluate(node.slice.step) if getattr(node.slice, "step", None) is not None else None
                return value[slice(lower, upper, step)]
            else:
                if hasattr(ast, "Index") and isinstance(node.slice, ast.Index):
                    slice_val = self.evaluate(node.slice.value)  # type: ignore
                else:
                    slice_val = self.evaluate(node.slice)
                return value[slice_val]
        elif isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            elif isinstance(node.op, ast.Mod):
                return left % right
            raise TypeError(f"不支持的二元操作符类型: {type(node.op)}")
        elif isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.evaluate(comparator)
                if isinstance(op, ast.Eq):
                    if not (left == right):
                        return False
                elif isinstance(op, ast.NotEq):
                    if not (left != right):
                        return False
                elif isinstance(op, ast.Lt):
                    if not (left < right):
                        return False
                elif isinstance(op, ast.LtE):
                    if not (left <= right):
                        return False
                elif isinstance(op, ast.Gt):
                    if not (left > right):
                        return False
                elif isinstance(op, ast.GtE):
                    if not (left >= right):
                        return False
                elif isinstance(op, ast.In):
                    if left not in right:
                        return False
                elif isinstance(op, ast.NotIn):
                    if not (left not in right):
                        return False
                else:
                    raise TypeError(f"不支持的比较操作符类型: {type(op)}")
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    if not self.evaluate(v):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for v in node.values:
                    if self.evaluate(v):
                        return True
                return False
        elif isinstance(node, ast.UnaryOp):
            operand = self.evaluate(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            elif isinstance(node.op, ast.USub):
                return -operand
            raise TypeError(f"不支持的一元操作符类型: {type(node.op)}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in self.allowed_calls:
                args = [self.evaluate(arg) for arg in node.args]
                return self.allowed_calls[node.func.id](*args)
            raise ValueError(f"不支持的函数调用: {node.func}")
        elif isinstance(node, ast.Attribute):
            value = self.evaluate(node.value)
            if isinstance(value, dict):
                return value.get(node.attr)
            raise TypeError("不支持的属性访问。仅支持对字典(dict)内的键进行属性读取。")
        raise TypeError(f"不支持的 AST 节点类型: {type(node)}")


def safe_eval(expr_str: str, context: dict) -> Any:
    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
        evaluator = SafeEvaluator(context)
        return evaluator.evaluate(tree)
    except Exception as e:
        raise ValueError(f"表达式解析评估失败: {e}")


def _deep_get(val: Any, path: str) -> Any:
    """支持点号分割的深层字典结构值获取"""
    if not path:
        return None
    keys = path.split(".")
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val


def render_template(template: str, variables: dict) -> str:
    """
    自定义模板渲染引擎，替代 str.format()。
    支持点号路径导航嵌套字典结构，支持列表数字索引，缺失路径返回空字符串。
    {var}         → variables["var"]
    {var.field}   → variables["var"]["field"]
    {var.list.0}  → variables["var"]["list"][0]
    dict/list 自动序列化为 JSON。
    """

    def _resolve(match):
        path = match.group(1).strip()
        if not path:
            return ""
        parts = path.split(".")
        value = variables
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(value):
                    value = value[idx]
                else:
                    return ""
            else:
                return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    # (?!\s*[:,}])：排除 JSON/Python 字面量强特征——
    # `}` 后跟 冒号(dict)、逗号(集合/数组)、右花括号(嵌套结尾) 的不视为变量引用，
    # 避免模板里的 `{a:1}`/`{a,b}`/`{"k":1}}` 等字面量片段被当变量吞成空串。
    # （带引号 JSON `{"a":1}` 因 `"` 不在字符类本就不匹配，此处仅补防裸键字面量。）
    return re.sub(r"\{([a-zA-Z0-9_.]+)\}(?!\s*[:,}])", _resolve, template)


def strip_braces(val: str) -> str:
    """剥离变量名两端可能的花括号，如 '{query}' → 'query'。"""
    if val.startswith("{") and val.endswith("}"):
        return val[1:-1].strip()
    return val


def camel_to_snake(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def convert_keys_to_snake(d: Any, depth: int = 0) -> Any:
    if depth > 100:
        raise RecursionError("Maximum recursion depth exceeded in convert_keys_to_snake")
    if isinstance(d, dict):
        return {camel_to_snake(k): convert_keys_to_snake(v, depth + 1) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_snake(x, depth + 1) for x in d]
    return d


# 条件分流节点类型集合：这些节点的出边由运行时条件路由决定，不参与静态边处理和环检测
CONDITIONAL_NODE_TYPES = {"condition", "intent_classifier", "switch"}

# 子图执行节点类型：循环体在编译时提取为独立子图，运行时按序/并发调用
SUBGRAPH_NODE_TYPES = {"loop_controller", "batch_processor"}

# 不支持单节点测试的节点类型集合（无执行逻辑、依赖子图、或需人工交互）
UNTESTABLE_NODE_TYPES = {"start", "end", "loop_controller", "batch_processor", "human_input", "loop_body_group"}


def validate_graph(graph_json: dict[str, Any]) -> None:
    """
    工作流图拓扑结构校验，验证完整性与防错
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    # 显式校验每个节点 id/type 必填，给出友好错误而非静默跳过或裸 KeyError
    for idx, n in enumerate(nodes):
        if not n.get("id"):
            raise ValueError(f"第 {idx + 1} 个节点缺少 id 字段。")
        if not n.get("type"):
            raise ValueError(f"节点 '{n['id']}' 缺少 type 字段。")

    nodes_map = {n["id"]: n for n in nodes if "id" in n}

    node_ids = {n["id"] for n in nodes if "id" in n}
    node_types = {n["id"]: n.get("type") for n in nodes if "id" in n}

    # 1. 缺少 START 节点校验
    start_nodes = [nid for nid, t in node_types.items() if t == "start"]
    if len(start_nodes) == 0:
        raise ValueError("工作流定义必须包含一个 'start' (开始) 节点。")
    if len(start_nodes) > 1:
        raise ValueError("工作流定义不能包含多个 'start' (开始) 节点。")

    # 2. 悬空边与重复边校验
    seen_edges = set()
    for i, edge in enumerate(edges):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            raise ValueError(f"第 {i + 1} 条连线缺少 source 或 target 属性。")
        if source not in node_ids:
            raise ValueError(f"连线引用的源节点 ID '{source}' 在节点列表中不存在。")
        if target not in node_ids:
            raise ValueError(f"连线引用的目标节点 ID '{target}' 在节点列表中不存在。")

        edge_key = (source, target)
        if edge_key in seen_edges:
            raise ValueError(f"连线重复：从 '{source}' 到 '{target}' 的连线被定义了多次。")
        seen_edges.add(edge_key)

    # 3. 子图节点体路由校验
    for n in nodes:
        ntype = n.get("type")
        if ntype in SUBGRAPH_NODE_TYPES:
            config = convert_keys_to_snake(n.get("config", {}))
            node_name = n.get("name", n["id"])

            # 优先尝试 parentNode（group 容器）模式
            parent_result = _find_body_nodes_by_parent(nodes, edges, n["id"])
            if parent_result[0]:
                body_node_ids = parent_result[0]
            else:
                # 回退到 BFS 模式（旧工作流）
                body_route = config.get("loop_body_route")
                if not body_route:
                    raise ValueError(f"节点 '{node_name}' 未配置循环体入口节点。")
                if body_route not in node_ids:
                    raise ValueError(f"节点 '{node_name}' 的循环体入口 '{body_route}' 不存在。")
                body_node_ids = _find_body_nodes(n["id"], body_route, edges)

            # 从画布边推导退出路径：穿透 group 容器
            exit_targets = []
            for edge in edges:
                if edge["source"] != n["id"]:
                    continue
                tgt = edge["target"]
                if tgt in body_node_ids or tgt == n["id"]:
                    continue
                tgt_type = node_types.get(tgt)
                if tgt_type == "loop_body_group":
                    # 穿透 group：查找 group → X 的出边作为实际退出目标
                    for g_edge in edges:
                        if g_edge["source"] == tgt:
                            g_tgt = g_edge["target"]
                            if g_tgt not in body_node_ids and g_tgt != n["id"]:
                                exit_targets.append(g_tgt)
                else:
                    exit_targets.append(tgt)
            if not exit_targets:
                raise ValueError(
                    f"节点 '{node_name}' 没有指向循环体外部的连线。请为循环控制节点添加一条连向后续节点的出边。"
                )

            # 检查体入口歧义
            if body_node_ids:
                entries = [
                    nid
                    for nid in body_node_ids
                    if not any(e["target"] == nid and e["source"] in body_node_ids for e in edges)
                ]
                if len(entries) > 1:
                    names = [nodes_map[eid].get("label", eid) for eid in entries if eid in nodes_map]
                    raise ValueError(f"循环体有多个可能的入口节点: {', '.join(names)}。请用连线明确节点执行顺序。")
                if len(entries) == 0 and len(body_node_ids) > 0:
                    raise ValueError("循环体内部存在环路，无法确定入口节点。")

    # 4. 孤立节点校验（子图体节点豁免：它们通过回边连向父节点，不在主图直接连通）
    # 先收集所有子图节点的体节点 ID，这些节点不需要在主图中表现为"已连通"
    all_body_node_ids = set()
    for n in nodes:
        ntype = n.get("type")
        if ntype in SUBGRAPH_NODE_TYPES:
            parent_result = _find_body_nodes_by_parent(nodes, edges, n["id"])
            if parent_result[0]:
                all_body_node_ids.update(parent_result[0])
            else:
                config = convert_keys_to_snake(n.get("config", {}))
                body_entry = config.get("loop_body_route")
                if body_entry and body_entry in node_ids:
                    all_body_node_ids.update(_find_body_nodes(n["id"], body_entry, edges))

    _iso_group_to_controller = _build_group_to_controller_map(nodes, edges, nodes_map)

    connected_nodes = set()
    for edge in edges:
        s, t = edge["source"], edge["target"]
        s_type = node_types.get(s)
        # source 是 group 时替换为对应 controller
        if s_type == "loop_body_group":
            s = _iso_group_to_controller.get(s, s)
        # target 是 group 时不计入连通性（group 是纯视觉节点）
        if node_types.get(t) == "loop_body_group":
            connected_nodes.add(s)
            continue
        connected_nodes.add(s)
        connected_nodes.add(t)

    for nid, ntype in node_types.items():
        if (
            ntype not in ("start", "end", "loop_body_group")
            and nid not in connected_nodes
            and nid not in all_body_node_ids
        ):
            node_name = nid
            for n in nodes:
                if n.get("id") == nid:
                    node_name = n.get("name", nid)
                    break
            raise ValueError(f"检测到孤立的工作节点 '{node_name}' (ID: {nid})，必须为它建立输入和输出连线。")

    # 5. 无条件静态环路检测 (DFS 环检测)
    # 仅针对非条件节点的静态连线建图（条件节点能基于运行时决策打破环路）
    _v_group_to_controller = _build_group_to_controller_map(nodes, edges, nodes_map)

    adj = {nid: [] for nid in node_ids}

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        source_type = node_types.get(source)

        # 穿透 group：source 是 group 时替换为对应 controller
        if source_type == "loop_body_group":
            source = _v_group_to_controller.get(source)
            if not source:
                continue
            source_type = node_types.get(source)
        # target 是 group 的边不参与主图环检测
        if node_types.get(target) == "loop_body_group":
            continue

        if source_type not in CONDITIONAL_NODE_TYPES:
            adj[source].append(target)

    # DFS 状态跟踪：0 = 未访问, 1 = 正在访问, 2 = 已完全访问
    visit_state = {nid: 0 for nid in node_ids}

    def dfs_has_cycle(u: str) -> bool:
        visit_state[u] = 1  # 正在访问
        for v in adj[u]:
            if visit_state[v] == 1:
                return True
            if visit_state[v] == 0:
                if dfs_has_cycle(v):
                    return True
        visit_state[u] = 2  # 已完全访问
        return False

    for nid in node_ids:
        if visit_state[nid] == 0:
            if dfs_has_cycle(nid):
                node_name = nid
                for n in nodes:
                    if n.get("id") == nid:
                        node_name = n.get("name", nid)
                        break
                raise ValueError(
                    f"检测到无条件死循环：静态流程在节点 '{node_name}' (ID: {nid}) 附近形成了闭环且没有任何判定条件分支。"
                )

    # 6. 模型节点配置完整性校验
    model_required_types = {"llm", "intent_classifier", "image_generator"}
    for n in nodes:
        ntype = n.get("type")
        if ntype in model_required_types:
            config = n.get("config", {})
            if not config:
                node_name = n.get("name", n["id"])
                raise ValueError(f"节点 '{node_name}' 缺少配置信息。")
            profile_code = config.get("modelProfileCode", "")
            if not profile_code or not profile_code.strip():
                node_name = n.get("name", n["id"])
                raise ValueError(f"节点 '{node_name}' 未选择模型 Profile，请先在配置面板中选择一个模型。")


def _build_group_to_controller_map(nodes: list, edges: list, nodes_map: dict) -> dict[str, str]:
    group_to_controller = {}
    for node in nodes:
        if node.get("type") == "loop_body_group":
            cfg = convert_keys_to_snake(node.get("config", {}))
            ctrl = cfg.get("controller_node_id")
            if ctrl:
                group_to_controller[node["id"]] = ctrl
            else:
                for edge in edges:
                    if edge.get("target") == node["id"]:
                        src_id = edge.get("source")
                        src_node = nodes_map.get(src_id)
                        if src_node and src_node.get("type") in ["loop_controller", "batch_processor"]:
                            group_to_controller[node["id"]] = src_id
                            break
    return group_to_controller


# --- 子图工具函数 ---


def _find_body_nodes(parent_id: str, body_entry_id: str, edges: list) -> set[str]:
    """BFS 从 body_entry_id 出发，沿 forward edges 遍历，直到遇到 parent_id 停止。"""
    if body_entry_id == parent_id:
        raise ValueError(
            f"循环体入口节点不能指向循环控制节点自身 (ID: {parent_id})。请选择一个不同的节点作为循环体入口。"
        )
    body_nodes = set()
    queue = collections.deque([body_entry_id])
    visited = set()

    while queue:
        current = queue.popleft()
        if current in visited or current == parent_id:
            continue
        visited.add(current)
        body_nodes.add(current)

        for edge in edges:
            if edge["source"] == current:
                target = edge["target"]
                if target not in visited:
                    queue.append(target)

    return body_nodes


def _find_body_nodes_by_parent(nodes: list, edges: list, controller_id: str) -> tuple[set[str], str | None]:
    """
    通过 parentNode 字段识别体节点（前端 group 容器模式）。
    流程：controller config.bodyGroupId → 找 group 子节点 → 推导入口。
    返回 (body_node_ids, body_entry_id)，未找到时返回 (set(), None)。
    """
    ctrl_node = next((n for n in nodes if n["id"] == controller_id), None)
    if not ctrl_node:
        return set(), None
    config = convert_keys_to_snake(ctrl_node.get("config", {}))
    group_id = config.get("body_group_id")
    if not group_id:
        # 尝试从边推导：找源头为 controller，目标为 loop_body_group 节点的边
        for e in edges:
            if e["source"] == controller_id:
                tgt_node = next((n for n in nodes if n["id"] == e["target"]), None)
                if tgt_node and tgt_node.get("type") == "loop_body_group":
                    group_id = tgt_node["id"]
                    break

    if not group_id:
        return set(), None

    # 找 parentNode == group_id 的节点
    body_node_ids = {n["id"] for n in nodes if n.get("parentNode") == group_id}
    if not body_node_ids:
        return set(), None

    # 推导体入口：group 内没有来自 group 内部入边的节点
    body_entry = None
    for nid in body_node_ids:
        has_internal_incoming = any(e["target"] == nid and e["source"] in body_node_ids for e in edges)
        if not has_internal_incoming:
            body_entry = nid
            break
    if not body_entry:
        body_entry = next(iter(body_node_ids))

    return body_node_ids, body_entry


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
                    rest = sh[len("intent_"):]
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
                    rest = sh[len("case_"):]
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


def resolve_node_inputs(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """根据节点配置中的 inputs schema 或 input_mappings 解析最终输入。"""
    input_mappings = config.get("input_mappings", {})
    inputs_schema = config.get("inputs", [])

    if inputs_schema and isinstance(inputs_schema, list):
        node_inputs = {}
        for inp in inputs_schema:
            name = inp.get("name")
            source = inp.get("source")
            if name and isinstance(source, list) and len(source) == 2:
                # source[0] 是 nodeId, source[1] 是级联选择器中绑定的值（前端已改为 variableName）
                # 注意：如果 source[1] 包含点号（如 LLM节点_output.topic），需进行深层查找
                var_key = source[1]
                val = None
                if var_key:
                    val = _deep_get(variables, var_key)
                # 兼容单节点测试：单节点测试时，前端直接把形如 {"input_1": "xxx"} 的 mock 数据当作 variables 传入。
                # 只有当按上游路径无法获取值，并且 name 在 variables 中确实存在时，才应用此 fallback，避免污染。
                if val is None and name in variables:
                    val = variables.get(name)
                node_inputs[name] = val
    else:
        node_inputs = apply_input_mappings(variables, input_mappings)

    return node_inputs


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """LangGraph reducer：合并多个节点对 variables 的并发更新"""
    return {**(left or {}), **(right or {})}


def _last_writer_wins(left: str, right: str) -> str:
    """LangGraph reducer：并行节点更新 current_node 时取最后一个"""
    return right


# --- 1. 统一状态定义 ---
class WorkflowState(TypedDict):
    """
    工作流运行时状态共享上下文
    """

    messages: Annotated[list, lambda left, right: (left or []) + (right or [])]
    variables: Annotated[dict[str, Any], _merge_dicts]
    current_node: Annotated[str, _last_writer_wins]


# --- 2. 节点处理器注册表 ---
class NodeExecutorRegistry:
    """
    节点执行器注册表，支持未来灵活扩展新的节点类型
    """

    def __init__(self):
        self._executors: dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]] = {}

    def register(self, node_type: str, executor_func: Callable[[dict[str, Any], dict[str, Any]], Any]):
        """
        注册一个节点执行函数。
        执行函数参数：(state: dict, config: dict) -> Dict[str, Any] (返回要更新的状态增量)
        """
        self._executors[node_type] = executor_func

    def get(self, node_type: str) -> Callable[[dict[str, Any], dict[str, Any]], Any] | None:
        return self._executors.get(node_type)


node_registry = NodeExecutorRegistry()


def apply_input_mappings(global_vars: dict, mappings: dict) -> dict:
    """根据映射配置提取节点需要的入参"""
    node_inputs = {}
    if not mappings:
        # 未配置输入映射的节点：透传全局变量，保证提示词模板里的 {变量} 能正常渲染。
        # 执行器（如 execute_llm_node）直接用本返回值渲染 prompt，返回 {} 会导致变量全部丢失。
        return global_vars

    for param_name, source_path in mappings.items():
        if isinstance(source_path, str) and source_path.startswith("variables."):
            var_key = source_path.removeprefix("variables.")
            node_inputs[param_name] = _deep_get(global_vars, var_key)
        else:
            node_inputs[param_name] = source_path
    return node_inputs


def apply_output_mappings(global_vars: dict, result: dict, mappings: dict) -> dict:
    """根据映射配置将节点输出回写全局共享变量"""
    if not mappings:
        return {**global_vars, **result}
    updated_vars = {**global_vars}
    for result_key, target_path in mappings.items():
        if isinstance(target_path, str) and target_path.startswith("variables."):
            var_key = target_path.removeprefix("variables.")
            updated_vars[var_key] = result.get(result_key)
        else:
            updated_vars[result_key] = result.get(result_key)
    return updated_vars


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
                except Exception as e:
                    if attempt >= max_attempts:
                        # 重试耗尽：抛 NodeExecutionError 携带 node_id，供上层写 failed_node_id
                        raise NodeExecutionError(node_id, attempt, e) from e
                    delay = float(backoff_base) * (2 ** (attempt - 1))
                    logger.warning(
                        "节点 '%s' 第 %d/%d 次执行失败，%.1fs 后重试: %s",
                        node_id, attempt, max_attempts, delay, e,
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
                # 如果求值失败，默认走向 false 路由并记录错误
                logger.error(f"[Workflow Router Error] Safe evaluate '{expression}' failed: {e}")
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
