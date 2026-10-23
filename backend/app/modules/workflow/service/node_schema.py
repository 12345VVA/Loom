"""节点 config 声明式 schema 与必填校验（三期B6 / WF-P2-5 + WF-P2-12）。

validate_graph 在编译前按本表逐节点校验必填字段与类型，消除
「配置不全 → 运行期静默走默认/空转」的静默失败面。

权威键名为前端 camelCase（图 JSON 原生形态）；对存量 snake_case 配置
（如 variable_transform 历史图、手工构造的图 JSON）按 camel→snake
自动双风格匹配。校验只在执行/编译入口生效，不阻断保存草稿。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.workflow.service.expressions import camel_to_snake


@dataclass(frozen=True)
class FieldSpec:
    """单个 config 字段的声明：键名、是否必填、允许类型、错误消息中文名。"""

    key: str  # camelCase 权威键（与前端图 JSON 一致）
    label: str  # 错误消息里的中文字段名
    required: bool = False
    types: tuple[type, ...] = (str,)


def _is_blank(val: Any) -> bool:
    """必填判定：None / 空白字符串 / 空列表 / 空字典 视为缺失。"""
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def get_config_value(config: dict[str, Any], key: str) -> Any:
    """双风格取值：camelCase 权威键优先，miss 时回落 snake_case（存量图兼容）。"""
    if key in config:
        return config[key]
    return config.get(camel_to_snake(key))


def validate_node_config(node_type: str, config: dict[str, Any], node_name: str) -> None:
    """按 schema 校验单节点 config；不合规抛 ValueError（中文友好消息）。"""
    schema = NODE_CONFIG_SCHEMA.get(node_type)
    if not schema:
        return
    for field in schema:
        val = get_config_value(config, field.key)
        if field.required and _is_blank(val):
            raise ValueError(
                f"节点 '{node_name}' 缺少必填配置「{field.label}」（{field.key}）。请在节点配置面板中补全后重新保存。"
            )
        if not _is_blank(val) and not isinstance(val, field.types):
            type_names = "/".join(t.__name__ for t in field.types)
            raise ValueError(
                f"节点 '{node_name}' 的配置「{field.label}」（{field.key}）类型不正确："
                f"期望 {type_names}，实际为 {type(val).__name__}。"
            )


# 各节点类型的 config schema（仅声明需要校验的字段；未列出的节点/字段不校验）。
# 必填判定依据执行器语义：缺失会导致静默空转或恒真/恒假等不可直觉行为。
#
# F3（UI/UX 审查 2026-10-10）：本表升级为前后端共同的必填口径单一来源——
# 经 dump_node_manifest.py 导出 configFields 供前端 getMissingConfigFields 派生，
# 消除「前端手工 switch / 面板星号 / 后端 schema」三处漂移（WFU-H10~H13）。
NODE_CONFIG_SCHEMA: dict[str, tuple[FieldSpec, ...]] = {
    # 条件表达式缺失时编译期兜底 "True"（恒真），用户难以察觉分支永不生效——必填
    "condition": (FieldSpec("expression", label="条件表达式", required=True, types=(str,)),),
    # switch 无 variable/cases 时路由器恒走 default（或 END），静默吞掉分流语义——必填
    "switch": (
        FieldSpec("variable", label="分支变量", required=True, types=(str,)),
        FieldSpec("cases", label="分支列表", required=True, types=(list,)),
    ),
    # loop/batch 列表变量缺失/为空时执行器静默返回空 results（空转）——必填
    "loop_controller": (FieldSpec("listVariable", label="循环列表变量", required=True, types=(str,)),),
    "batch_processor": (FieldSpec("batchListVariable", label="批处理列表变量", required=True, types=(str,)),),
    # 复审 P1-9：与前端 getMissingConfigFields 口径对齐——此前 UI 必填但 API 直存
    # 的图后端放行，运行时空 prompt 直接调模型 / 空 toolCode 落 "unknown" 查找失败。
    # intent 的 intents 不列（空 intents 语义合法：不经过 LLM 直落 default_route，
    # 三期B6 决策）。modelProfileCode 并入本表（F3）：与 graph_validate step6
    # 同性质双保险，前端警示条得以从 manifest 统一派生。
    "llm": (
        FieldSpec("promptTemplate", label="提示词模板", required=True, types=(str,)),
        FieldSpec("modelProfileCode", label="AI 模型", required=True, types=(str,)),
    ),
    "tool_executor": (FieldSpec("toolCode", label="工具", required=True, types=(str,)),),
    # 长期记忆写入：contentTemplate 缺失/为空时无内容可记（静默空转类），编译期 fail-fast
    "memory_store": (FieldSpec("contentTemplate", label="记忆内容模板", required=True, types=(str,)),),
    # F3 补齐（前端已在查、后端原本未列，运行期静默空转/空 prompt 调模型）：
    "image_generator": (
        FieldSpec("promptTemplate", label="提示词模板", required=True, types=(str,)),
        FieldSpec("modelProfileCode", label="AI 模型", required=True, types=(str,)),
        # IP 资产库（设计 1.2）：可选资产引用说明，不进必填校验（存量图安全）；
        # 运行期语义见 node_executors.execute_image_generator_node 的 Composer 插桩
        FieldSpec("characterId", label="引用角色资产", required=False, types=(int,)),
        FieldSpec("sceneId", label="引用场景资产", required=False, types=(int,)),
        FieldSpec("styleId", label="引用风格资产", required=False, types=(int,)),
    ),
    # intent_classifier 整条不进 schema：其 modelProfileCode 是「intents 非空时才必填」
    # 的条件语义（空 intents 直落 default_route 不调模型），静态 FieldSpec 装不下——
    # 由 graph_validate step6 保持条件校验为权威，前端警示条随 manifest 派生后不报
    # intent（保存/运行期仍被 step6 拦截，错误消息可定位）。
    # 提示消息为空时审批人看到空卡片（interrupt 无内容）——必填
    "human_input": (FieldSpec("message", label="提示消息", required=True, types=(str,)),),
    # 赋值规则为空时节点为纯占位（无任何副作用）——必填
    "variable_assignment": (FieldSpec("assignments", label="赋值规则", required=True, types=(list,)),),
    # 输入变量/转换类型缺失时执行器空转；outputVariable 不列（有 transformed_value
    # 默认名 + 前端新建自动生成，非必填）
    "variable_transform": (
        FieldSpec("inputVariable", label="输入变量", required=True, types=(str,)),
        FieldSpec("transformType", label="转换类型", required=True, types=(str,)),
    ),
}


# 输出变量默认名的后端权威表（三期B7 / WF-P2-8）：与各执行器
# config.get("output_variable", <默认>) 一一对应，经 manifest 导出供前端
# 新建节点初值消费——前端不再手写默认名（human_input 曾漂移为
# approval_status，后端运行时真实语义是 approval_result）。
NODE_OUTPUT_VAR_DEFAULTS: dict[str, str] = {
    "llm": "output",  # node_executors.execute_llm_node
    "human_input": "approval_result",  # execute_human_input_node
    "loop_controller": "loop_results",  # execute_loop_controller_node
    "batch_processor": "batch_results",  # execute_batch_processor_node
    "image_generator": "image_url",  # execute_image_generator_node
    "tool_executor": "tool_result",  # execute_tool_executor_node
    # 前端写驼峰 outputVariable（三期B7 统一），编译期 convert_keys_to_snake
    # 转为 output_variable 后由执行器读取
    "variable_transform": "transformed_value",  # execute_variable_transform_node
    "memory_store": "memory_id",  # execute_memory_store_node（memory_action 为固定名次变量，不随改名）
    "memory_recall": "memories",  # execute_memory_recall_node（memory_recall_status 为固定名次变量）
}
