"""
工作流表达式求值与模板渲染（纯函数，由 compiler.py 门面 re-export）。

- SafeEvaluator / safe_eval：白名单 AST 求值器，杜绝代码注入
- render_template：{var} / {var.field} / {var.list.0} 插值
- convert_keys_to_snake：前端 camelCase config → 后端 snake_case
"""

import ast
import json
import re
from typing import Any


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
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            # 集合/序列字面量：支持 `status in ['a', 'b']`、`x not in (1, 2)` 这类常见判定
            items = [self.evaluate(elt) for elt in node.elts]
            if isinstance(node, ast.Tuple):
                return tuple(items)
            if isinstance(node, ast.Set):
                return set(items)
            return items
        elif isinstance(node, ast.Dict):
            # 字典字面量：支持 `d == {'k': 1}`。解包（**）无键可求值，显式拒绝
            if any(k is None for k in node.keys):
                raise ValueError("安全求值不支持字典解包（**）")
            return {self.evaluate(k): self.evaluate(v) for k, v in zip(node.keys, node.values)}
        elif isinstance(node, ast.IfExp):
            # 三元表达式：a if cond else b
            return self.evaluate(node.body) if self.evaluate(node.test) else self.evaluate(node.orelse)
        elif isinstance(node, ast.FormattedValue):
            # f-string 的插值段：先应用 conversion（!r/!s/!a），再应用 format_spec ——
            # 这是 Python 的求值顺序（conversion 在前，format_spec 作用在转换结果上）。
            # node.conversion 为 int：-1 表示未指定、'r'/'s'/'a' 对应其 ASCII 码。
            val = self.evaluate(node.value)
            if node.conversion == ord("r"):
                val = repr(val)
            elif node.conversion == ord("s"):
                val = str(val)
            elif node.conversion == ord("a"):
                val = ascii(val)
            if node.format_spec is not None:
                return format(val, self.evaluate(node.format_spec))
            return val
        elif isinstance(node, ast.JoinedStr):
            # f-string 整体：逐段拼接（内部 Constant 段本身已是 str）
            return "".join(str(self.evaluate(v)) for v in node.values)
        raise TypeError(f"不支持的 AST 节点类型: {type(node)}")


def safe_eval(expr_str: str, context: dict) -> Any:
    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
        evaluator = SafeEvaluator(context)
        return evaluator.evaluate(tree)
    except Exception as e:
        raise ValueError(f"表达式解析评估失败: {e}")


def _deep_get(val: Any, path: str) -> Any:
    """支持点号分割的深层字典结构值获取（list 支持数字索引段，口径与 render_template 一致）"""
    if not path:
        return None
    keys = path.split(".")
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        elif isinstance(val, list) and k.isdigit():
            idx = int(k)
            val = val[idx] if 0 <= idx < len(val) else None
        else:
            return None
    return val


# 变量引用字符集必须与前端 sanitizeLabel（useNodeFactory.ts 的 [^a-zA-Z0-9_一-鿿]）
# 严格一致 —— U+4E00–U+9FFF（CJK 统一汉字）。否则前端能生成中文变量名（如「意图分类_output」），
# 后端却不识别，导致模板插值被静默跳过。
_VAR_REF_PATTERN = re.compile(r"\{([a-zA-Z0-9_.一-鿿]+)\}(?!\s*[:,}])")


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
    return _VAR_REF_PATTERN.sub(_resolve, template)


def strip_braces(val: str) -> str:
    """剥离变量名两端可能的花括号，如 '{query}' → 'query'。"""
    if val.startswith("{") and val.endswith("}"):
        return val[1:-1].strip()
    return val


def strip_var_prefix(val: str) -> str:
    """全局变量名归一（复审 P0/P1 修复）：剥花括号后再剥 `variables.` 前缀。

    前端变量引用文案（getVariableRefText）对 condition/tool_executor 生成
    `variables.变量名`，用户复制进 switch 判断变量 / transform 输入变量 /
    loop 列表变量等字段时保持该形态——所有「跨节点全局读取」入口统一经本
    helper 归一为裸键名，`variables.foo` 与 `foo` 两种写法等价。
    """
    name = strip_braces(val or "")
    return name.removeprefix("variables.")


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
