"""
工作流动态编译器与节点注册表。
"""
import ast
import json
import logging
import re
from typing import Any, Annotated, Callable, Dict, TypedDict, Optional

logger = logging.getLogger(__name__)
from langgraph.graph import StateGraph, START, END


class SafeEvaluator:
    def __init__(self, context: dict):
        self.context = context
        self.allowed_calls = {
            'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool
        }

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
            slice_val = self.evaluate(node.slice)
            return value[slice_val]
        elif isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Add): return left + right
            elif isinstance(node.op, ast.Sub): return left - right
            elif isinstance(node.op, ast.Mult): return left * right
            elif isinstance(node.op, ast.Div): return left / right
            elif isinstance(node.op, ast.Mod): return left % right
            raise TypeError(f"不支持的二元操作符类型: {type(node.op)}")
        elif isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.evaluate(comparator)
                if isinstance(op, ast.Eq):
                    if not (left == right): return False
                elif isinstance(op, ast.NotEq):
                    if not (left != right): return False
                elif isinstance(op, ast.Lt):
                    if not (left < right): return False
                elif isinstance(op, ast.LtE):
                    if not (left <= right): return False
                elif isinstance(op, ast.Gt):
                    if not (left > right): return False
                elif isinstance(op, ast.GtE):
                    if not (left >= right): return False
                elif isinstance(op, ast.In):
                    if not (left in right): return False
                elif isinstance(op, ast.NotIn):
                    if not (left not in right): return False
                else:
                    raise TypeError(f"不支持的比较操作符类型: {type(op)}")
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            values = [self.evaluate(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            elif isinstance(node.op, ast.Or):
                return any(values)
        elif isinstance(node, ast.UnaryOp):
            operand = self.evaluate(node.operand)
            if isinstance(node.op, ast.Not): return not operand
            elif isinstance(node.op, ast.USub): return -operand
            raise TypeError(f"不支持的一元操作符类型: {type(node.op)}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in self.allowed_calls:
                args = [self.evaluate(arg) for arg in node.args]
                return self.allowed_calls[node.func.id](*args)
            raise ValueError(f"不支持的函数调用: {node.func}")
        elif isinstance(node, ast.Attribute):
            value = self.evaluate(node.value)
            if isinstance(value, dict) and node.attr in value:
                return value[node.attr]
            raise TypeError("不支持的属性访问。仅支持对字典(dict)内的键进行属性读取。")
        raise TypeError(f"不支持的 AST 节点类型: {type(node)}")


def safe_eval(expr_str: str, context: dict) -> Any:
    try:
        tree = ast.parse(expr_str.strip(), mode='eval')
        evaluator = SafeEvaluator(context)
        return evaluator.evaluate(tree)
    except Exception as e:
        raise ValueError(f"表达式解析评估失败: {e}")


def render_template(template: str, variables: dict) -> str:
    """
    自定义模板渲染引擎，替代 str.format()。
    支持点号路径导航嵌套字典结构，缺失路径返回空字符串。
    {var}         → variables["var"]
    {var.field}   → variables["var"]["field"]
    dict/list 自动序列化为 JSON。
    """
    def _resolve(match):
        path = match.group(1).strip()
        if not path:
            return ''
        parts = path.split('.')
        value = variables
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return ''
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return re.sub(r'\{([^}]+)\}', _resolve, template)


def camel_to_snake(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()


def convert_keys_to_snake(d: Any) -> Any:
    if isinstance(d, dict):
        return {camel_to_snake(k): convert_keys_to_snake(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_snake(x) for x in d]
    return d


def validate_graph(graph_json: Dict[str, Any]) -> None:
    """
    工作流图拓扑结构校验，验证完整性与防错
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

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
            raise ValueError(f"第 {i+1} 条连线缺少 source 或 target 属性。")
        if source not in node_ids:
            raise ValueError(f"连线引用的源节点 ID '{source}' 在节点列表中不存在。")
        if target not in node_ids:
            raise ValueError(f"连线引用的目标节点 ID '{target}' 在节点列表中不存在。")

        edge_key = (source, target)
        if edge_key in seen_edges:
            raise ValueError(f"连线重复：从 '{source}' 到 '{target}' 的连线被定义了多次。")
        seen_edges.add(edge_key)

    # 3. 孤立节点校验
    connected_nodes = set()
    for edge in edges:
        connected_nodes.add(edge["source"])
        connected_nodes.add(edge["target"])
    
    for nid, ntype in node_types.items():
        if ntype not in ("start", "end") and nid not in connected_nodes:
            node_name = nid
            for n in nodes:
                if n.get("id") == nid:
                    node_name = n.get("name", nid)
                    break
            raise ValueError(f"检测到孤立的工作节点 '{node_name}' (ID: {nid})，必须为它建立输入和输出连线。")

    # 4. 无条件静态环路检测 (DFS 环检测)
    # 仅针对静态直接连线建图（排除从判断、分支和循环控制器发出的条件流，因为它们能基于运行时决策打破环路）
    conditional_node_types = {"condition", "intent_classifier", "loop_controller", "switch"}
    adj = {nid: [] for nid in node_ids}
    
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        source_type = node_types.get(source)
        edge_type = edge.get("type", "direct")
        
        if edge_type == "direct" and source_type not in conditional_node_types:
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
                raise ValueError(f"检测到无条件死循环：静态流程在节点 '{node_name}' (ID: {nid}) 附近形成了闭环且没有任何判定条件分支。")

    # 5. 模型节点配置完整性校验
    model_required_types = {"llm", "intent_classifier", "batch_processor", "image_generator"}
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


def _merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
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
    messages: Annotated[list, lambda l, r: (l or []) + (r or [])]
    variables: Annotated[Dict[str, Any], _merge_dicts]
    current_node: Annotated[str, _last_writer_wins]


# --- 2. 节点处理器注册表 ---
class NodeExecutorRegistry:
    """
    节点执行器注册表，支持未来灵活扩展新的节点类型
    """
    def __init__(self):
        self._executors: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}

    def register(self, node_type: str, executor_func: Callable[[Dict[str, Any], Dict[str, Any]], Any]):
        """
        注册一个节点执行函数。
        执行函数参数：(state: dict, config: dict) -> Dict[str, Any] (返回要更新的状态增量)
        """
        self._executors[node_type] = executor_func

    def get(self, node_type: str) -> Optional[Callable[[Dict[str, Any], Dict[str, Any]], Any]]:
        return self._executors.get(node_type)


node_registry = NodeExecutorRegistry()


def apply_input_mappings(global_vars: dict, mappings: dict) -> dict:
    """根据映射配置提取节点需要的入参"""
    node_inputs = {}
    if not mappings:
        return global_vars
    for param_name, source_path in mappings.items():
        if isinstance(source_path, str) and source_path.startswith("variables."):
            var_key = source_path.removeprefix("variables.")
            node_inputs[param_name] = global_vars.get(var_key)
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
    def compile_graph(cls, graph_json: Dict[str, Any]) -> StateGraph:
        """
        根据前端配置的拓扑 JSON 编译成 LangGraph 图
        """
        # 0. 校验拓扑数据结构与完整性
        if not isinstance(graph_json, dict) or "nodes" not in graph_json or "edges" not in graph_json:
            raise ValueError("工作流拓扑结构不合法，必须包含 nodes 和 edges 字段。")

        # 严格验证图结构完整性
        validate_graph(graph_json)

        # 创建工作流状态图
        builder = StateGraph(WorkflowState)

        # 获取所有节点定义
        nodes = graph_json.get("nodes", [])
        edges = graph_json.get("edges", [])

        # 预先构建散列表映射，将查找复杂度由 O(N*M) 降至 O(N+M)
        nodes_map = {n["id"]: n for n in nodes}

        # 1. 遍历注册所有工作节点
        for node in nodes:
            node_id = node["id"]
            node_type = node["type"]
            node_config = convert_keys_to_snake(node.get("config", {}))

            # 跳过开始辅助节点（结束节点需要注册为执行节点以处理输出模板）
            if node_type == "start":
                continue

            # 为当前节点构造执行包装器
            builder.add_node(
                node_id,
                cls.create_node_runner(node_id, node_type, node_config)
            )

        # 2. 遍历并建立普通连线关系
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            edge_type = edge.get("type", "direct")

            # 处理边界节点 (O(1) 散列映射)
            source_node = nodes_map.get(source)
            target_node = nodes_map.get(target)

            source_type = source_node.get("type") if source_node else None
            target_type = target_node.get("type") if target_node else None

            # 从 START 连接
            if source_type == "start":
                builder.add_edge(START, target)
                continue

            # 连接到结束节点（结束节点执行后自动连向 END）
            if target_type == "end":
                builder.add_edge(source, target)
                continue

            # 条件连接由条件节点专门处理，普通连线直接建立
            if edge_type == "direct":
                builder.add_edge(source, target)

        # 2.5 结束节点统一连向 END
        for node in nodes:
            if node.get("type") == "end":
                builder.add_edge(node["id"], END)

        # 3. 遍历并处理条件边与分流节点
        for node in nodes:
            node_id = node["id"]
            node_type = node["type"]
            node_config = convert_keys_to_snake(node.get("config", {}))

            if node_type == "condition":
                true_route = node_config.get("true_route")
                false_route = node_config.get("false_route")
                if true_route and false_route:
                    builder.add_conditional_edges(
                        node_id,
                        cls.create_conditional_router(node_id, node_config),
                        {true_route: true_route, false_route: false_route}
                    )

            elif node_type == "intent_classifier":
                intents = node_config.get("intents", [])
                default_route = node_config.get("default_route")
                path_map = {}
                for intent in intents:
                    target = intent.get("target_route")
                    if target:
                        path_map[target] = target
                if default_route:
                    path_map[default_route] = default_route

                if path_map:
                    builder.add_conditional_edges(
                        node_id,
                        cls.create_intent_router(node_id, node_config),
                        path_map
                    )

            elif node_type == "loop_controller":
                loop_body = node_config.get("loop_body_route")
                exit_route = node_config.get("exit_route")
                if loop_body and exit_route:
                    builder.add_conditional_edges(
                        node_id,
                        cls.create_loop_router(node_id, node_config),
                        {loop_body: loop_body, exit_route: exit_route}
                    )

            elif node_type == "switch":
                cases = node_config.get("cases", [])
                default_route = node_config.get("default_route")
                path_map = {}
                for case in cases:
                    target = case.get("target_route")
                    if target:
                        path_map[target] = target
                if default_route:
                    path_map[default_route] = default_route

                if path_map:
                    builder.add_conditional_edges(
                        node_id,
                        cls.create_switch_router(node_id, node_config),
                        path_map
                    )

        return builder

    @classmethod
    def create_node_runner(cls, node_id: str, node_type: str, config: Dict[str, Any]):
        """
        生成一个满足 LangGraph 要求的节点运行函数
        """
        async def node_runner(state: WorkflowState) -> Dict[str, Any]:
            # 记录当前执行节点
            state["current_node"] = node_id
            
            # 获取对应的注册执行器
            executor = node_registry.get(node_type)
            if not executor:
                raise ValueError(f"工作流中使用了未注册的节点类型: '{node_type}'")

            # 1. 应用输入变量映射，提炼入参
            input_mappings = config.get("input_mappings", {})
            node_inputs = apply_input_mappings(state["variables"], input_mappings)

            # 2. 运行执行器
            updates = await executor(node_inputs, config)
            if updates is None:
                updates = {}

            # 3. 应用输出变量映射，写回全局状态
            output_mappings = config.get("output_mappings", {})
            new_variables = apply_output_mappings(state["variables"], updates, output_mappings)
            
            return {
                "variables": new_variables,
                "current_node": node_id
            }
        return node_runner

    @classmethod
    def create_conditional_router(cls, node_id: str, config: Dict[str, Any]):
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
                return true_route if result else false_route
            except Exception as e:
                # 如果求值失败，默认走向 false 路由并记录错误
                logger.error(f"[Workflow Router Error] Safe evaluate '{expression}' failed: {e}")
                return false_route

        return conditional_router

    @classmethod
    def create_intent_router(cls, node_id: str, config: Dict[str, Any]):
        """
        生成意图分类分支路由逻辑
        """
        def intent_router(state: WorkflowState) -> str:
            target_route = state.get("variables", {}).get(f"{node_id}_selected_route")
            return target_route or config.get("default_route")
        return intent_router

    @classmethod
    def create_loop_router(cls, node_id: str, config: Dict[str, Any]):
        """
        生成循环遍历路由逻辑
        """
        def loop_router(state: WorkflowState) -> str:
            target_route = state.get("variables", {}).get(f"{node_id}_next_route")
            return target_route or config.get("exit_route")
        return loop_router

    @classmethod
    def create_switch_router(cls, node_id: str, config: Dict[str, Any]):
        """
        生成 Switch-Case 多路分支的动态路由逻辑
        """
        def switch_router(state: WorkflowState) -> str:
            var_name = config.get("variable", "")
            val = state.get("variables", {})
            if var_name.startswith("variables."):
                var_key = var_name.removeprefix("variables.")
                val = val.get(var_key)
            else:
                val = val.get(var_name)
                
            cases = config.get("cases", [])
            default_route = config.get("default_route")
            
            for case in cases:
                case_val_str = str(case.get("value", ""))
                if str(val) == case_val_str:
                    return case.get("target_route") or default_route
            return default_route
        return switch_router
