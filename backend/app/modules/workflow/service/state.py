"""
工作流运行时状态定义、节点执行器注册表与输入/输出映射（由 compiler.py 门面 re-export）。

node_registry 单例在本模块持有；node_executors 经 import 副作用完成注册。
"""

from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from app.modules.workflow.service.expressions import _deep_get


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

    （原 messages 死字段已移除：带拼接 reducer 却无任何执行器读写，白占
    checkpoint 与循环迭代拷贝——核实清单 WF-P2-13。如未来需要对话历史，
    按需以独立通道 reintroduce。）
    """

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
