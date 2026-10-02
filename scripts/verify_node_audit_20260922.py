"""工作流节点模块修复回归基线（断言版）。

对审查报告中确认的缺陷逐条做最小复现与**期望值断言**：修复前部分断言为红，
修复后应全绿。用于每个修复批次改完后跑同一条命令做回归。

在 backend/ 目录下用 venv 解释器运行：
    cd backend && venv\\Scripts\\python.exe ..\\scripts\\verify_node_audit_20260922.py

断言分组：
    [A] render_template 支持中文变量名          （P0-2）
    [B] SafeEvaluator 支持集合/容器字面量        （P1-1）
    [C] 循环/批处理可用 _deep_get 解析点号路径    （P1-2）
    [D] create_node_runner 放行 GraphInterrupt  （P0-1）
    [E] _parse_llm_output 容忍前置引导词         （P2-2）
    [F] 边界探针：中文变量在其它解析路径可用      （P0-2 断点唯一性）
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import app.modules.workflow.service.workflow_service as ws  # noqa: E402,F401  触发执行器注册
from app.modules.workflow.service.compiler import (  # noqa: E402
    WorkflowCompiler,
    WorkflowState,
    _deep_get,
    render_template,
    safe_eval,
)

SEP = "=" * 72
_RESULTS: list[tuple[str, str, str]] = []  # (分组, 用例名, 结果)


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def check(group: str, name: str, actual: object, expected: object) -> bool:
    """断言 actual == expected，并记账。"""
    ok = actual == expected
    _RESULTS.append((group, name, "PASS" if ok else "FAIL"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        print(f"         期望: {expected!r}")
        print(f"         实际: {actual!r}")
    return ok


def check_no_raise(group: str, name: str, fn) -> tuple[bool, object]:
    """断言 fn() 不抛异常，返回 (ok, value)。"""
    try:
        value = fn()
    except BaseException as e:  # noqa: BLE001
        _RESULTS.append((group, name, "FAIL"))
        print(f"  [FAIL] {name} —— 意外异常 {type(e).__name__}: {str(e)[:120]}")
        return False, None
    _RESULTS.append((group, name, "PASS"))
    print(f"  [PASS] {name} -> {value!r}")
    return True, value


def _safe(expr: str, ctx: dict):
    """safe_eval 包装：异常时返回异常描述字符串，便于 check 断言直接看差异。"""
    try:
        return safe_eval(expr, ctx)
    except Exception as e:  # noqa: BLE001
        return f"<{type(e).__name__}: {str(e)[:90]}>"


# ---------------------------------------------------------------- [A] 中文变量名
def case_a_unicode_template() -> None:
    section("[A] render_template 中文变量名（P0-2）")
    variables = {"意图分类_output": "分类结果A", "llm_output": {"text": "hello"}, "甲": {"乙": [9]}}

    ok, out = check_no_raise(
        "A", "中文变量插值（不抛异常）", lambda: render_template("请根据 {意图分类_output} 生成内容", variables)
    )
    if ok:
        check("A", "中文变量被替换为真实值", out, "请根据 分类结果A 生成内容")

    check("A", "ASCII 变量仍正常（无回归）", render_template("v={llm_output.text}", variables), "v=hello")
    check("A", "中文 + 点号路径", render_template("{甲.乙}", variables), "[9]")
    check("A", "未定义变量 → 空串", render_template("x={不存在的变量}", variables), "x=")


# ---------------------------------------------------------------- [B] 集合字面量
def case_b_safe_eval_literals() -> None:
    section("[B] SafeEvaluator 集合/容器字面量（P1-1）")
    check("B", "status in [..]", _safe("status in ['success','approved']", {"status": "success"}), True)
    check("B", "user_type not in (..)", _safe("user_type not in (1, 2)", {"user_type": 3}), True)
    check("B", "tags == [..]", _safe("tags == ['a','b']", {"tags": ["a", "b"]}), True)
    check("B", "d == {..}", _safe("d == {'k': 1}", {"d": {"k": 1}}), True)
    check("B", "set 字面量成员判定", _safe("x in {'a', 'b'}", {"x": "a"}), True)
    check("B", "既有：and / 比较（无回归）", _safe("count > 1 and name == 'a'", {"count": 3, "name": "a"}), True)


# ---------------------------------------------------------------- [C] 深层取值
def case_c_deep_get() -> None:
    section("[C] 循环/批处理点号路径取值（P1-2）")
    variables = {"llm_output": {"user_list": [1, 2, 3]}, "flat_list": ["a"]}

    check("C", "_deep_get 点号路径", _deep_get(variables, "llm_output.user_list"), [1, 2, 3])
    check("C", "_deep_get 扁平键与 .get 等价", _deep_get(variables, "flat_list"), variables.get("flat_list"))
    check("C", "_deep_get 缺失路径返回 None", _deep_get(variables, "nope.deep"), None)
    check("C", "_deep_get 空串返回 None", _deep_get(variables, ""), None)
    # 缺陷证据：执行器原写法对点号路径必然取不到值
    check("C", "缺陷证明：dict.get 取不到点号路径", variables.get("llm_output.user_list"), None)


# ---------------------------------------------------------------- [D] 控制流放行
async def case_d_graph_interrupt() -> None:
    section("[D] create_node_runner 放行 GraphInterrupt（P0-1）")
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    for attempts in (1, 3):
        cfg = {"retry_max_attempts": attempts, "retry_backoff_base": 0.01, "message": "请审批"}
        runner = WorkflowCompiler.create_node_runner("hi_1", "human_input", cfg)
        builder = StateGraph(WorkflowState)
        builder.add_node("hi_1", runner)
        builder.add_edge(START, "hi_1")
        builder.add_edge("hi_1", END)
        graph = builder.compile(checkpointer=InMemorySaver())

        label = f"图产出 __interrupt__（attempts={attempts}）"
        try:
            out = await graph.ainvoke(
                {"variables": {"a": 1}, "messages": [], "current_node": ""},
                {"configurable": {"thread_id": f"t{attempts}"}},
            )
        except BaseException as e:  # noqa: BLE001
            _RESULTS.append(("D", label, "FAIL"))
            print(f"  [FAIL] {label}")
            print(f"         抛出 {type(e).__name__}: {str(e)[:150]}")
            cause = getattr(e, "__cause__", None)
            if cause is not None:
                print(f"         原始 cause: {type(cause).__name__}: {str(cause)[:110]}")
            continue

        check("D", label, "__interrupt__" in out, True)
        if "__interrupt__" in out:
            interrupts = out["__interrupt__"]
            payload = getattr(interrupts[0], "value", None) if interrupts else None
            check("D", f"中断载荷含审批提示（attempts={attempts}）", (payload or {}).get("message"), "请审批")


# ---------------------------------------------------------------- [E] LLM JSON
def case_e_llm_json_parse() -> None:
    section("[E] _parse_llm_output 容忍引导词（P2-2）")
    parse = ws._parse_llm_output

    check("E", "纯 JSON", parse('{"data": 1}', "json", "out"), {"out": {"data": 1}})
    check("E", "裸代码块", parse('```json\n{"data": 1}\n```', "json", "out"), {"out": {"data": 1}})
    check(
        "E",
        "前置引导词 + 代码块",
        parse('好的，输出如下：\n```json\n{"data": 1}\n```', "json", "out"),
        {"out": {"data": 1}},
    )
    check("E", "前置引导词 + 裸 JSON", parse('解析结果：{"data": 1}', "json", "out"), {"out": {"data": 1}})
    check("E", "数组 JSON", parse("[1, 2]", "json", "out"), {"out": [1, 2]})
    check("E", "纯文本模式不解析（无回归）", parse('{"data": 1}', "text", "out"), {"out": '{"data": 1}'})

    ok, res = check_no_raise("E", "彻底非 JSON 不抛异常", lambda: parse("完全不是 JSON 的一段话", "json", "out"))
    if ok:
        check("E", "彻底非 JSON 的降级结果（保留原文）", res, {"out": "完全不是 JSON 的一段话"})


# ---------------------------------------------------------------- [F] 边界探针
def case_f_boundary_probe() -> None:
    section("[F] 边界探针：中文变量在其它解析路径（P0-2 断点唯一性）")
    ctx = {"状态": "ok", "count": 3, "甲": {"乙": [9]}}

    check("F", "safe_eval 中文字典键查找", _safe("状态 == 'ok'", ctx), True)
    check("F", "_deep_get 中文键 + 点号", _deep_get(ctx, "甲.乙"), [9])
    check("F", "render_template 中文键 + 点号", render_template("{甲.乙}", ctx), "[9]")

    print("  以下为 SafeEvaluator 已知未支持语法，本次不修，仅记录现状（不判定，避免误判为回归）：")
    for expr in ("'a' if count > 1 else 'b'", 'f"v={count}"'):
        print(f"         {expr:28s} -> {_safe(expr, ctx)!r}")


# ---------------------------------------------------------------- [G] 源码锚点
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_COMPILER = os.path.join(_ROOT, "backend", "app", "modules", "workflow", "service", "compiler.py")
_SERVICE = os.path.join(_ROOT, "backend", "app", "modules", "workflow", "service", "workflow_service.py")
_FRONTEND = os.path.join(_ROOT, "frontend", "src", "modules", "workflow")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def case_g_source_anchors() -> None:
    """源码锚点静态校验：防止后续重构把已修项回退掉。"""
    section("[G] 源码锚点（防回退）")
    compiler_src = _read(_COMPILER)
    service_src = _read(_SERVICE)

    check("G", "compiler 导入 GraphBubbleUp", "from langgraph.errors import GraphBubbleUp" in compiler_src, True)
    check("G", "compiler 重试处放行 GraphBubbleUp", "except GraphBubbleUp:" in compiler_src, True)
    check("G", "compiler 使用 _VAR_REF_PATTERN 常量", "_VAR_REF_PATTERN = re.compile" in compiler_src, True)
    check("G", "render_template 走 _VAR_REF_PATTERN", "_VAR_REF_PATTERN.sub(_resolve, template)" in compiler_src, True)
    # 注意：不能用 "节点 '%s'" 做锚点——重试日志里也有同样片段，会误判为已修
    check("G", "路由求值失败日志带 node_id", "[Workflow Router Error] 节点" in compiler_src, True)

    check("G", "service 导入 _deep_get", "_deep_get," in service_src, True)
    check("G", "循环+批处理改用 _deep_get（≥2 处）", service_src.count("_deep_get(variables, list_var)") >= 2, True)
    check("G", "service 无遗留 variables.get(list_var)", "variables.get(list_var)" not in service_src, True)
    check("G", "意图标签归一化函数存在", "_normalize_intent_label" in service_src, True)
    check("G", "LLM JSON 使用 raw_decode 逐点提取", "raw_decode" in service_src, True)

    utils_src = _read(os.path.join(_FRONTEND, "utils.ts"))
    check("G", "utils.ts 导出 resolveOutputVar", "export function resolveOutputVar" in utils_src, True)
    for rel in (
        os.path.join("utils", "graph-validator.ts"),
        os.path.join("composables", "useNodeFactory.ts"),
        os.path.join("composables", "useUpstreamVariables.ts"),
    ):
        src = _read(os.path.join(_FRONTEND, rel))
        check("G", f"{rel} 调用 resolveOutputVar", "resolveOutputVar(" in src, True)


# ---------------------------------------------------------------- 汇总
def main() -> int:
    case_a_unicode_template()
    case_b_safe_eval_literals()
    case_c_deep_get()
    asyncio.run(case_d_graph_interrupt())
    case_e_llm_json_parse()
    case_f_boundary_probe()
    case_g_source_anchors()

    section("汇总")
    groups: dict[str, list[str]] = {}
    for group, _name, result in _RESULTS:
        groups.setdefault(group, []).append(result)

    total = len(_RESULTS)
    failed = [r for r in _RESULTS if r[2] == "FAIL"]
    for group in sorted(groups):
        results = groups[group]
        passed = results.count("PASS")
        print(f"  [{'OK ' if passed == len(results) else 'RED'}] {group}: {passed}/{len(results)}")

    print(f"\n  合计 {total - len(failed)}/{total} 通过")
    if failed:
        print("\n  未通过明细：")
        for group, name, _ in failed:
            print(f"    - [{group}] {name}")
    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
