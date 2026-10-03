"""架构守卫测试：防止反向依赖恶化、防止元数据缺表、防止循环依赖引入。"""

import ast
import unittest
from collections import defaultdict
from pathlib import Path

from sqlmodel import SQLModel

# 确保在导入测试时 core.database 已被加载
import app.core.database  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_ROOT / "app"
CORE_DIR = APP_DIR / "core"
FRAMEWORK_DIR = APP_DIR / "framework"

# framework/ 对业务模块的反向依赖执行「存量容忍、增量冻结」决议
# （deliverables/框架倒挂依赖核实-2026-10-02.md §四"明确不做"保留的存量）。
# 条目级快照：(相对 framework/ 的 posix 路径, 导入的 app.modules 模块)。
# 口径为全 AST import（顶层 11 处 + 函数内延迟 1 处 = 12 条二元组）；
# compat_aliases.py 映射表/auto_router.py docstring 里的字符串路径不是 import，不入快照。
# 白名单外任何新增——新文件引入、既有文件新增 import（含函数体内）、更换子模块路径——一律失败；
# 扩白名单属有意决策，请更新此快照并在注释说明理由。
FRAMEWORK_REVERSE_DEPENDENCY_WHITELIST = frozenset(
    {
        ("middleware/admin_authority.py", "app.modules.base.service.authority_service"),
        ("middleware/operation_log.py", "app.modules.base.model.sys"),
        ("middleware/rate_limit.py", "app.modules.base.service.cache_service"),
        ("middleware/scope_authority.py", "app.modules.base.service.authority_service"),
        ("router/compat_aliases.py", "app.modules.base.compat"),
        ("router/compat_aliases.py", "app.modules.base.model.sys"),
        ("router/query_builder.py", "app.modules.base.service.data_scope_service"),
    }
)

# core/ 的函数内延迟 import 冻结（core 顶层静态 import 由独立守卫全面禁止）。
# 现状：security.py 3 处延迟导入（cache_set/cache_get/increment_user_token_version），
# 按模块去重后 2 个二元组；database.py 的 _autodiscover_models 走 import_module 动态
# 导入，AST 静态不可见，天然不在扫描范围。
CORE_LAZY_MODULES_IMPORTS_WHITELIST = frozenset(
    {
        ("security.py", "app.modules.base.service.cache_service"),
        ("security.py", "app.modules.base.service.authority_service"),
    }
)


def _get_top_level_app_imports(file_path: Path) -> set[str]:
    """提取文件顶层（非函数体内）导入的 app.* 模块。"""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError:
        return set()

    imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app"):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if not node.level and node.module and node.module.startswith("app"):
                imports.add(node.module)
    return imports


def _get_all_app_imports(file_path: Path) -> set[str]:
    """提取文件全 AST（含函数体内延迟 import）导入的 app.* 模块。"""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError:
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app"):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if not node.level and node.module and node.module.startswith("app"):
                imports.add(node.module)
    return imports


class ArchitectureGuardTests(unittest.TestCase):
    def test_metadata_contains_all_tables(self):
        """断言 metadata 收集了全量表，且不遗漏 workflow_annotation 和 workflow_definition_version。"""
        tables = set(SQLModel.metadata.tables.keys())
        self.assertIn(
            "workflow_annotation",
            tables,
            "SQLModel.metadata 缺少 workflow_annotation 表",
        )
        self.assertIn(
            "workflow_definition_version",
            tables,
            "SQLModel.metadata 缺少 workflow_definition_version 表",
        )
        self.assertGreaterEqual(
            len(tables),
            38,
            f"SQLModel.metadata 表总数异常，预期 >= 38，实际为 {len(tables)}",
        )

    def test_core_has_no_static_modules_imports(self):
        """断言 app/core 下的任何模块均不得在顶层静态 import app.modules.*。"""
        violations = []
        for py_file in CORE_DIR.glob("*.py"):
            imports = _get_top_level_app_imports(py_file)
            for imp in imports:
                if imp.startswith("app.modules"):
                    violations.append(f"{py_file.name} 顶层静态导入了: {imp}")

        self.assertEqual(
            violations,
            [],
            "发现 app/core 存在顶层静态依赖业务模块 app.modules:\n" + "\n".join(violations),
        )

    def test_core_lazy_modules_imports_frozen(self):
        """断言 app/core 的函数内延迟 import app.modules 不超过「存量容忍」快照。

        顶层静态 import 由 test_core_has_no_static_modules_imports 全面禁止；
        本守卫冻结延迟导入增量（security.py 的缓存/权限调用），防止借函数体
        逃避静态检查的新增反向依赖。
        """
        current: set = set()
        for py_file in CORE_DIR.glob("*.py"):
            for imp in _get_all_app_imports(py_file):
                if imp.startswith("app.modules"):
                    current.add((py_file.name, imp))

        unexpected = current - CORE_LAZY_MODULES_IMPORTS_WHITELIST
        self.assertEqual(
            unexpected,
            set(),
            "app/core 出现白名单外的延迟导入业务模块（存量容忍、增量冻结）：\n"
            + "\n".join(f"  {f} -> {m}" for f, m in sorted(unexpected)),
        )

        stale = CORE_LAZY_MODULES_IMPORTS_WHITELIST - current
        self.assertEqual(
            stale,
            set(),
            "core 延迟导入白名单快照存在已不存在的条目，请同步收窄快照：\n"
            + "\n".join(f"  {f} -> {m}" for f, m in sorted(stale)),
        )

    def test_framework_reverse_dependency_whitelist(self):
        """断言 app/framework 对 app.modules 的反向依赖（含函数内延迟 import）不超过「存量容忍」快照。

        与 test_no_circular_dependencies 互补：SCC 守卫拦"已成环"（启动失败风险），
        本守卫拦"未成环的增量侵蚀"（framework 引叶子模块不会成环，SCC 检测不到）。
        口径为全 AST：函数体内延迟 import 同样冻结（顶层之外的盲区不再放行新增）。
        """
        current: set = set()
        for py_file in FRAMEWORK_DIR.rglob("*.py"):
            rel = py_file.relative_to(FRAMEWORK_DIR).as_posix()
            for imp in _get_all_app_imports(py_file):
                if imp.startswith("app.modules"):
                    current.add((rel, imp))

        unexpected = current - FRAMEWORK_REVERSE_DEPENDENCY_WHITELIST
        self.assertEqual(
            unexpected,
            set(),
            "app/framework 出现白名单外的业务模块反向依赖（存量容忍、增量冻结）：\n"
            + "\n".join(f"  {f} -> {m}" for f, m in sorted(unexpected)),
        )

        # 反向对账：存量依赖被理顺移除是好事，但快照必须同步收窄，防止白名单变成失真的死角
        stale = FRAMEWORK_REVERSE_DEPENDENCY_WHITELIST - current
        self.assertEqual(
            stale,
            set(),
            "白名单快照存在已不存在的条目，请同步收窄快照：\n" + "\n".join(f"  {f} -> {m}" for f, m in sorted(stale)),
        )

    def test_no_circular_dependencies(self):
        """断言系统全量 200+ 模块顶层导入无循环依赖（Tarjan SCC 算法检测）。"""
        mods: dict[str, Path] = {}
        for p in APP_DIR.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(BACKEND_ROOT).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mod_name = ".".join(parts)
            mods[mod_name] = p

        graph: dict[str, set[str]] = defaultdict(set)
        for name, path in mods.items():
            for target in _get_top_level_app_imports(path):
                if target in mods:
                    graph[name].add(target)
                else:
                    parts = target.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        cand = ".".join(parts[:i])
                        if cand in mods:
                            graph[name].add(cand)
                            break

        # Tarjan 算法
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
                if len(comp) > 1:
                    sccs.append(comp)

        for v in sorted(mods):
            if v not in index:
                strongconnect(v)

        self.assertEqual(
            sccs,
            [],
            f"检测到真实循环依赖 (SCC size > 1):\n{sccs}",
        )


if __name__ == "__main__":
    unittest.main()
