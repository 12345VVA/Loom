"""静态分析 app 包导入图，检测真实循环依赖（SCC）——治理方案 G2 转正版。

与 backend/tests/test_arch_guard.py 的分工：
- 守卫测试：CI 门禁，SCC 目前只扫顶层 AST（函数体内延迟导入是守卫自认的盲区，
  G4 解耦完成后守卫切换全量口径）；
- 本脚本：诊断工具，默认全量 AST（含函数体内延迟导入与 TYPE_CHECKING 块），
  并解析相对导入，给出比守卫更严格的耦合视图。

发现真环（SCC size>1）或自环时退出码 1，可直接当 gate 用。

用法（仓库根目录）：
    python scripts/verify_arch_cycle.py             # 全量 AST（严格视图，默认）
    python scripts/verify_arch_cycle.py --top-only  # 仅顶层（与守卫同口径对照）
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend"
APP = ROOT / "app"


def mod_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_import_from(mod: str, node: ast.ImportFrom) -> str | None:
    """把 ImportFrom 解析为绝对目标模块串（相对导入按当前模块包定位）。"""
    if node.level == 0:
        return node.module
    # level=1 指当前包，每多一级向上一跳
    pkg_parts = mod.split(".")[:-1]
    up = node.level - 1
    if up:
        if up > len(pkg_parts):
            return None
        pkg_parts = pkg_parts[:-up]
    if node.module:
        return ".".join([*pkg_parts, node.module])
    return ".".join(pkg_parts) or None


def collect_imports(tree: ast.AST, mod: str, top_only: bool) -> set[str]:
    """收集模块依赖的 app.* 目标集合。

    top_only=True 时只取模块顶层（与 test_arch_guard 的 SCC 口径一致）；
    默认 ast.walk 全量收集——延迟导入与 TYPE_CHECKING 块同样是架构耦合。
    """
    out: set[str] = set()
    nodes = tree.body if top_only else ast.walk(tree)
    for node in nodes:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("app"):
                    out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            target = resolve_import_from(mod, node)
            if target and target.startswith("app"):
                out.add(target)
    return out


def main() -> int:
    top_only = "--top-only" in sys.argv

    mods: dict[str, Path] = {}
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        mods[mod_name(p)] = p

    graph: dict[str, set[str]] = defaultdict(set)
    parse_errors: list[str] = []

    for name, path in mods.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            parse_errors.append(f"{name}: {e}")
            continue
        for target in collect_imports(tree, name, top_only):
            # app.a.b 命中 app.a.b.c 时, 建立到最具体的已存在模块的边
            if target in mods:
                graph[name].add(target)
            else:
                parts = target.split(".")
                for i in range(len(parts) - 1, 0, -1):
                    cand = ".".join(parts[:i])
                    if cand in mods:
                        graph[name].add(cand)
                        break

    # Tarjan 强连通分量
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: set[str] = set()
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in sorted(mods):
        if v not in index:
            strongconnect(v)

    cycles = [c for c in sccs if len(c) > 1]
    self_loops = [m for m in sorted(mods) if m in graph.get(m, ())]

    mode = "顶层 AST（守卫口径）" if top_only else "全量 AST（严格口径）"
    print(f"扫描模式: {mode}")
    print(f"模块总数: {len(mods)}")
    print(f"import 边数: {sum(len(v) for v in graph.values())}")
    print(f"语法错误: {len(parse_errors)}")
    for e in parse_errors:
        print("   ", e)
    print()
    print(f"=== 真实循环依赖 (SCC size>1): {len(cycles)} 个 ===")
    for comp in sorted(cycles, key=len, reverse=True):
        print(f"\n[环] 规模 {len(comp)}")
        for m in sorted(comp):
            inside = sorted(graph.get(m, set()) & set(comp))
            print(f"   - {m}")
            for i in inside:
                print(f"       -> {i}")
    print()
    print(f"=== 自环: {len(self_loops)} ===")
    for m in self_loops:
        print("   -", m)

    if cycles or self_loops:
        print("\nFAIL: 存在真实循环依赖")
        return 1
    print("\nOK: 无循环依赖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
