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
    节点执行器注册表，支持未来灵活扩展新的节点类型。

    元数据（三期B6 / WF-P2-3）：
    - idempotent：重试安全性。非幂等节点（生图、循环/批处理等「重试 = 整体重跑」）
      由 _invoke_executor_with_retry 强制 max_attempts=1，防止重复计费/重复执行；
    - deprecated：已下架/不建议新用的节点类型（供 manifest 导出与前端物料过滤）。
    """

    def __init__(self):
        self._executors: dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]] = {}
        self._idempotency: dict[str, bool] = {}
        self._deprecated: dict[str, bool] = {}

    def register(
        self,
        node_type: str,
        executor_func: Callable[[dict[str, Any], dict[str, Any]], Any],
        *,
        idempotent: bool = True,
        deprecated: bool = False,
    ):
        """
        注册一个节点执行函数。
        执行函数参数：(state: dict, config: dict) -> Dict[str, Any] (返回要更新的状态增量)
        """
        self._executors[node_type] = executor_func
        self._idempotency[node_type] = idempotent
        self._deprecated[node_type] = deprecated

    def get(self, node_type: str) -> Callable[[dict[str, Any], dict[str, Any]], Any] | None:
        return self._executors.get(node_type)

    def is_idempotent(self, node_type: str) -> bool:
        """未注册类型视为幂等（未注册类型在执行前已被拦截，此处仅防御性默认）。"""
        return self._idempotency.get(node_type, True)

    def is_deprecated(self, node_type: str) -> bool:
        return self._deprecated.get(node_type, False)

    def types(self) -> list[str]:
        return list(self._executors.keys())


node_registry = NodeExecutorRegistry()


def resolve_node_inputs(
    variables: dict[str, Any], config: dict[str, Any], *, allow_mock_fallback: bool = False
) -> dict[str, Any]:
    """根据节点配置中的 inputs schema 或 input_mappings 解析最终输入。

    allow_mock_fallback（三期B4 / WF-P2-1）：仅单节点测试路径（run_node_standalone）
    开启——前端把 {"input_1": "xxx"} 形态的 mock 数据直接当 variables 传入，当按
    上游路径取不到值且同名键存在时回落 mock 值。整图执行路径恒为 False：
    上游未产出 → None 显性化，不再静默拿同名顶层变量顶替（有意语义收紧）。
    """
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
                # 兼容单节点测试的 mock fallback（见 docstring）：仅 standalone 路径开启
                if allow_mock_fallback and val is None and name in variables:
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


def compute_output_delta(result: dict, mappings: dict) -> dict:
    """计算节点的 applied delta（三期B5 / WF-P1-3）：仅返回本节点实际写入的键。

    - 无 output_mappings：executor updates 全键即增量；
    - 有 output_mappings：仅映射目标键进增量，取 result 值；未映射的 updates
      键被丢弃（原全量合并路径同样如此——非 variables. 前缀的 target 不生效）。

    取代原 apply_output_mappings（全量合并，并行分支快照互覆盖的根源，已随
    本批删除）。node_runner 返回 delta 而非全量快照后，LangGraph reducer
    {**left, **right} 的键级合并语义使并行分支各写各键、互不覆盖；图内 state
    经 reducer 累积仍是全量，路由器/loop/batch 的 ainvoke 消费方不受影响。
    """
    if not mappings:
        return dict(result or {})
    delta: dict[str, Any] = {}
    result = result or {}
    for result_key, target_path in mappings.items():
        if isinstance(target_path, str) and target_path.startswith("variables."):
            var_key = target_path.removeprefix("variables.")
            delta[var_key] = result.get(result_key)
        else:
            delta[result_key] = result.get(result_key)
    return delta
