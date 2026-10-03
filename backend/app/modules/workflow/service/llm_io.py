"""工作流 LLM 输入/输出处理纯函数群。

自 workflow_service.py 拆出：JSON Schema 构建、格式指令生成、
LLM 输出解析（三级降级）。全部为无副作用纯函数，供
node_executors（节点执行）与外部测试直接引用。
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# --- 1. 注册核心节点执行逻辑 ---


def _field_to_schema(f: dict) -> dict[str, Any]:
    field_type = f.get("type", "string").strip()
    desc = f.get("description", "").strip()

    schema = {}
    if desc:
        schema["description"] = desc

    if field_type == "object":
        schema["type"] = "object"
        properties = {}
        required = []
        for child in f.get("children") or []:
            child_name = child.get("name", "").strip()
            if not child_name or child_name == "[Item]":
                continue
            properties[child_name] = _field_to_schema(child)
            required.append(child_name)
        schema["properties"] = properties
        schema["required"] = required
        schema["additionalProperties"] = False

    elif field_type == "array_object":
        schema["type"] = "array"
        properties = {}
        required = []
        for child in f.get("children") or []:
            child_name = child.get("name", "").strip()
            if not child_name:
                continue
            properties[child_name] = _field_to_schema(child)
            required.append(child_name)
        schema["items"] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    elif field_type == "array_string":
        schema["type"] = "array"
        schema["items"] = {"type": "string"}

    elif field_type == "array_number":
        schema["type"] = "array"
        schema["items"] = {"type": "number"}

    elif field_type == "array_boolean":
        schema["type"] = "array"
        schema["items"] = {"type": "boolean"}

    elif field_type == "array":
        schema["type"] = "array"
        children = f.get("children") or []
        if children:
            schema["items"] = _field_to_schema(children[0])
        else:
            schema["items"] = {"type": "string"}

    else:
        # 兼容 OpenAI Schema 规范，确保 boolean, number/integer, string 类型正确
        schema["type"] = field_type

    return schema


def _build_json_schema_from_fields(
    json_fields: list[dict],
    schema_name: str = "workflow_output",
) -> dict[str, Any] | None:
    """
    将工作流 jsonFields [{name, type, description, children}] 转为 OpenAI 兼容的 JSON Schema。
    无有效字段时返回 None（调用方应回退到 json_object）。
    """
    if not json_fields:
        return None

    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in json_fields:
        name = f.get("name", "").strip()
        if not name or name == "[Item]":
            continue
        properties[name] = _field_to_schema(f)
        required.append(name)

    if not properties:
        return None

    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _build_json_desc_recursive(fields: list[dict], indent: int = 1) -> str:
    parts = []
    indent_space = "  " * indent
    for f in fields:
        name = f.get("name")
        if not name:
            continue
        desc = f.get("description", "")
        field_type = f.get("type", "string").strip()

        desc_str = f" ({desc})" if desc else ""

        if field_type == "object":
            children_str = _build_json_desc_recursive(f.get("children") or [], indent + 1)
            parts.append(f'{indent_space}"{name}": {{\n{children_str}\n{indent_space}}}')
        elif field_type == "array_object":
            children_str = _build_json_desc_recursive(f.get("children") or [], indent + 2)
            indent_next = "  " * (indent + 1)
            parts.append(
                f'{indent_space}"{name}": [\n{indent_next}{{\n{children_str}\n{indent_next}}}\n{indent_space}]'
            )
        elif field_type == "array_string":
            parts.append(f'{indent_space}"{name}": [string{desc_str}]')
        elif field_type == "array_number":
            parts.append(f'{indent_space}"{name}": [number{desc_str}]')
        elif field_type == "array_boolean":
            parts.append(f'{indent_space}"{name}": [boolean{desc_str}]')
        elif field_type == "array":
            children = f.get("children") or []
            if children:
                item_field = children[0]
                item_type = item_field.get("type", "string").strip()
                if item_type == "object":
                    item_str = _build_json_desc_recursive(item_field.get("children") or [], indent + 2)
                    indent_next = "  " * (indent + 1)
                    parts.append(
                        f'{indent_space}"{name}": [\n{indent_next}{{\n{item_str}\n{indent_next}}}\n{indent_space}]'
                    )
                else:
                    item_desc = item_field.get("description", "")
                    item_desc_str = f" ({item_desc})" if item_desc else ""
                    parts.append(f'{indent_space}"{name}": [{item_type}{item_desc_str}]')
            else:
                parts.append(f'{indent_space}"{name}": []')
        else:
            parts.append(f'{indent_space}"{name}": {field_type}{desc_str}')

    return ",\n".join(parts)


def _build_llm_response_format(output_format: str, json_fields: list) -> tuple[dict[str, Any] | None, str]:
    """根据输出模式构建 response_format 与追加到 prompt 的格式化指令。

    Tier 1: json_schema（有 jsonFields 时自动生成 Schema）；Tier 2: json_object（宽松模式）。
    返回 (response_format, format_instructions)。
    """
    response_format: dict[str, Any] | None = None
    format_instructions = ""

    if output_format == "json":
        # Tier 1: json_schema — 有字段定义时生成 Schema
        schema = _build_json_schema_from_fields(json_fields)
        if schema:
            response_format = schema
        else:
            # Tier 2: json_object — 无字段定义，宽松模式
            response_format = {"type": "json_object"}
        # 文本指令始终追加作为兜底
        if json_fields:
            field_desc = _build_json_desc_recursive(json_fields, 1)
            format_instructions = (
                f"\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。\n"
                f"JSON 结构如下：\n{{\n{field_desc}\n}}"
            )
        else:
            format_instructions = "\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。"
    elif output_format == "json_object":
        # Tier 2: json_object — 用户显式选择宽松模式
        response_format = {"type": "json_object"}
        format_instructions = "\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。"

    return response_format, format_instructions


# _extract_first_json 对每个 `{`/`[` 位置各调一次 raw_decode（用 raw_decode(raw, idx) 免去 raw[idx:] 切片）。
# 性能要点（两处，均已实测分离）：
#   - 畸形深嵌套（如 "[" * n）：每次 raw_decode 都要递归到 Python 递归上限才抛 RecursionError，
#     代价 ≈ 位置数 × 深度 —— 用 _MAX_JSON_RECURSION_FAILURES 作失败预算，命中即停。
#   - 成功候选多时：**旧的「包含判断」是 O(n²) 两两比对**，候选 10000 时约 1 亿次比较（可达秒级）。
#     已改为「按 start 升序、end 降序排序 + 单遍 max_end 扫描」的 O(n log n) 等价算法（见步骤 2）。
# _MAX_JSON_CANDIDATE_ATTEMPTS 为总体尝试上限（防病态洪泛，正常输入远达不到），命中任一上限即视为
# 扫描被截断 —— 宁可回落原文（返回 None），也不返回截断点之前可能残缺的片段（fail-safe）。
_MAX_JSON_CANDIDATE_ATTEMPTS = 10000
_MAX_JSON_RECURSION_FAILURES = 32


def _extract_first_json(raw: str) -> str | None:
    """定位文本中最可能的 JSON 片段（兼容前置引导词与说明性文字）。

    从每个 `{` / `[` 位置用 raw_decode 逐点尝试，而非贪婪正则匹配最外层括号 ——
    后者在文本含多个花括号片段时会吞掉过长区间，必然解析失败。

    候选选择三步：
      1. 收集所有可解析候选（尝试次数受两道上限约束，超限则整体回落原文）；
      2. 剔除被其他候选完全包含的片段，只留最外层（O(n log n) 排序 + 单遍扫描）——
         否则 `[{"a":1}]` 的内层 `{"a":1}` 会顶掉外层数组；
      3. 排序：**对象优先于数组**（治正文里 `[1,2]` 这类噪声：`步骤 [1,2] 见下 {"a":1}`
         取对象）；同类取最长，长度平手取位置最前。

    已知取舍（对象/数组混合场景的固有歧义）：当结果本身是数组、而正文另含对象片段时，
    「对象优先」会取对象（如 `输出 [{"id":1}] 说明 {}` 取 `{}`）。按类型或按长度选都必然
    在另一方向出错，故此处保留「对象优先」，不做进一步区分 —— 详见任务报告。
    """
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, int, str, bool]] = []  # (start, end, text, is_obj)
    attempts = 0
    recursion_failures = 0
    truncated = False
    for idx, ch in enumerate(raw):
        if ch not in "{[":
            continue
        if attempts >= _MAX_JSON_CANDIDATE_ATTEMPTS or recursion_failures >= _MAX_JSON_RECURSION_FAILURES:
            truncated = True
            break
        attempts += 1
        try:
            # raw_decode(raw, idx) 从 idx 起解析，返回的 end 已是**原字符串绝对下标**，省去 raw[idx:] 拷贝
            value, end = decoder.raw_decode(raw, idx)
        except RecursionError:
            # 畸形深嵌套（如 "[" * 3000）：每次都要递归到上限才抛，须计入预算并同等降级
            recursion_failures += 1
            continue
        except json.JSONDecodeError:
            continue
        candidates.append((idx, end, raw[idx:end], isinstance(value, dict)))

    # 扫描被截断 → 结果可能在截断点之后，回落原文（fail-safe）
    if truncated or not candidates:
        return None

    # 步骤 2：剔除被其他候选完全包含的片段，仅保留最外层。
    # 语义：cand 被 other 完全包含 ⟺ other.start <= cand.start 且 cand.end <= other.end
    #       且至少一侧严格（起点更早或终点更远）。包含者起点必 <= cand 起点，故按
    #       (start 升序, end 降序) 排序后单遍扫描：维护已见最大 end，若 cand.end <= max_end
    #       则存在更早起点、更远终点的候选吸收它 → 丢弃；否则保留并更新 max_end。
    # 该变换与旧 O(n²) 两两比对严格等价，但代价降到排序主导（候选 10000 由秒级降到毫秒级）。
    ordered = sorted(candidates, key=lambda c: (c[0], -c[1]))
    outermost: list[tuple[int, int, str, bool]] = []
    max_end = -1
    for cand in ordered:
        if cand[1] <= max_end:
            continue
        outermost.append(cand)
        max_end = cand[1]

    # 步骤 3：对象优先于数组；同类取最长，长度平手取最前
    def _rank(c: tuple[int, int, str, bool]) -> tuple[int, int, int]:
        _, _, _, is_obj = c
        return (0 if is_obj else 1, -(c[1] - c[0]), c[0])

    return min(outermost, key=_rank)[2]


def _parse_llm_output(content: str, output_format: str, output_variable: str) -> dict[str, Any]:
    """解析 LLM 输出。

    JSON 模式按三级降级：直接解析 → markdown 代码块 → 首个候选 JSON 片段
    （对象优先、剔除内层被包含片段，见 `_extract_first_json`）；
    全部失败才保留原始文本，保证下游拿到可读内容而不是异常。
    """
    if output_format in ("json", "json_object"):
        stripped = content.strip()

        # Tier 1：本身即合法 JSON（最快路径）
        try:
            return {output_variable: json.loads(stripped)}
        except (json.JSONDecodeError, RecursionError):
            # RecursionError：畸形深嵌套（如 "[" * 3000）会击穿 JSON 解析器，
            # 必须与解析失败同等降级，否则异常穿透节点、下游拿不到可读内容
            pass

        # Tier 2/3：代码块 → 首个 JSON 片段
        candidates: list[str] = []
        block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
        if block:
            candidates.append(block.group(1))
        extracted = _extract_first_json(stripped)
        if extracted:
            candidates.append(extracted)

        for candidate in candidates:
            try:
                return {output_variable: json.loads(candidate.strip())}
            except (json.JSONDecodeError, RecursionError):
                continue

        logger.warning("LLM JSON 输出解析失败，保留原始文本")
    return {output_variable: content}
