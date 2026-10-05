"""架构守卫测试：防止反向依赖恶化、防止元数据缺表、防止循环依赖引入。"""

import ast
import os
import subprocess
import sys
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

# framework/ 对业务模块的反向依赖已 DI 清零（runtime 注册表 + 定义下沉），
# 守卫语义从「存量容忍、增量冻结」升级为「全面禁止」：
# framework/ 下任何文件（含函数体内）出现 app.modules import 一律失败。
# 快照保留为空集合——如未来确需引入，属于架构级决策，须重开白名单并更新此注释。
FRAMEWORK_REVERSE_DEPENDENCY_WHITELIST = frozenset()

# core/ 的函数内延迟 import 已 DI 清零（security.py 经 framework runtime 注册表
# 解析缓存/令牌版本实现）。守卫语义升级为「core 全面禁止 app.modules」：
# database.py 的 _autodiscover_models 走 import_module 动态导入，AST 静态不可见，
# 天然不在扫描范围。
CORE_LAZY_MODULES_IMPORTS_WHITELIST = frozenset()

# 模块方向守卫（H4）：被消费的上游域禁止反向 import 其消费方。
# 依赖契约：workflow_annotation → workflow_eval → workflow → {ai, media, ...}，
# workflow 源码出现任何指向两个下游质量域的 import（含函数体内延迟 import）即失败。
# 需要新增方向规则时在此字典扩条目即可。
MODULE_DIRECTION_FORBIDDEN = {
    "app.modules.workflow": ("app.modules.workflow_eval", "app.modules.workflow_annotation"),
}


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


def _resolve_import_from(mod: str, node: ast.ImportFrom) -> str | None:
    """把 ImportFrom 解析为绝对目标模块串（相对导入按当前模块所在包定位）。"""
    if node.level == 0:
        return node.module
    pkg_parts = mod.split(".")[:-1]
    up = node.level - 1
    if up:
        if up > len(pkg_parts):
            return None
        pkg_parts = pkg_parts[:-up]
    if node.module:
        return ".".join([*pkg_parts, node.module])
    return ".".join(pkg_parts) or None


def _get_all_app_imports_resolved(file_path: Path, mod_name: str) -> set[str]:
    """全 AST 提取 app.* 导入并解析相对导入（跨域 SCC 与方向守卫的口径）。"""
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
            target = _resolve_import_from(mod_name, node)
            if target and target.startswith("app"):
                imports.add(target)
    return imports


def _module_domain(mod: str) -> str:
    """依赖域归属：app.core / app.framework / app.modules.<name> / 其他顶层。"""
    parts = mod.split(".")
    if len(parts) >= 2 and parts[1] in ("core", "framework"):
        return ".".join(parts[:2])
    if len(parts) >= 3 and parts[1] == "modules":
        return ".".join(parts[:3])
    return ".".join(parts[:2])


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

    def test_core_never_imports_framework(self):
        """断言 app/core 对 app.framework 零依赖（全 AST 含延迟 import，递归子目录）。

        core→framework 的唯一历史边（database.py 引 BaseEntity）已随 M9 定义下沉清零：
        BaseEntity 平移至 app/core/models/entity.py，framework/models/entity.py 留门面
        re-export。自此依赖方向单一：framework→core、modules→{core, framework}；
        core 出现任何指向 app.framework 的 import（含函数体内）一律失败。
        """
        violations = []
        for py_file in CORE_DIR.rglob("*.py"):
            for imp in _get_all_app_imports(py_file):
                if imp.startswith("app.framework"):
                    violations.append(f"{py_file.relative_to(CORE_DIR).as_posix()} -> {imp}")

        self.assertEqual(
            violations,
            [],
            "app/core 出现对 app.framework 的依赖（含延迟 import，全面禁止）：\n" + "\n".join(violations),
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

    def test_no_cross_domain_circular_dependencies(self):
        """跨域循环依赖守卫（H4/G4）：全量 AST（含函数体内延迟 import 与相对导入）
        建图后跑 Tarjan SCC，凡「横跨多个依赖域」的环一律失败。

        与 test_no_circular_dependencies 的分工：后者以顶层 AST 零容忍（同/跨域都拦），
        本守卫把盲区（lazy import）补上，但允许「同域内部环」——模块拆分后兄弟文件
        间的延迟互引是合法形态（2026-10-04 诊断实测 3 个环均为域内环）。
        真正危险的是跨域环（如 workflow ↔ workflow_eval），那是模块边界失守。
        """
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
            for target in _get_all_app_imports_resolved(path, name):
                if target in mods:
                    graph[name].add(target)
                else:
                    parts = target.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        cand = ".".join(parts[:i])
                        if cand in mods:
                            graph[name].add(cand)
                            break

        # Tarjan 算法（全量边）
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

        cross_domain = [c for c in sccs if len({_module_domain(m) for m in c}) > 1]
        self.assertEqual(
            cross_domain,
            [],
            "检测到跨依赖域循环依赖（模块边界失守，需架构级解耦）:\n"
            + "\n".join(f"  [{_module_domain(c[0])} ↔ ...] {c}" for c in cross_domain),
        )

    def test_module_dependency_direction(self):
        """模块方向守卫（H4/G4）：上游域禁止反向 import 消费方（含 lazy import）。

        依赖契约：workflow_annotation → workflow_eval → workflow 单向。eval→workflow
        指向 model 层不会回流成 SCC（跨域 SCC 守卫拦不住），必须用方向规则直接封死。
        """
        violations: list[str] = []
        for upstream, forbidden_domains in MODULE_DIRECTION_FORBIDDEN.items():
            upstream_dir = APP_DIR.joinpath(*upstream.split(".")[2:])
            for py_file in upstream_dir.rglob("*.py"):
                if "__pycache__" in py_file.parts:
                    continue
                rel = py_file.relative_to(BACKEND_ROOT).with_suffix("")
                parts = list(rel.parts)
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                mod_name = ".".join(parts)
                for target in _get_all_app_imports_resolved(py_file, mod_name):
                    for forbidden in forbidden_domains:
                        if target == forbidden or target.startswith(forbidden + "."):
                            violations.append(f"{mod_name} -> {target}")

        self.assertEqual(
            violations,
            [],
            "发现上游域反向依赖消费方（破坏 annotation→eval→workflow 单向契约）:\n" + "\n".join(violations),
        )

    def test_framework_independence(self):
        """框架独立性证明：framework 全部模块与 core.security 可完整导入（零 ImportError），
        运行时注册表对未注册依赖显式报错（DI 契约）。

        子进程内裸 import，模拟 framework 被抽取独立分发的最小场景。
        注：sys.modules 断言不适用——app.core.database 的 _autodiscover_models 是
        设计允许的模型注册权威（core→modules），会合法拉入业务模型模块；框架独立性
        的判据是「零 ImportError 可完整导入」+ DI 未装配显式失败。
        """
        code = (
            "import importlib, pkgutil\n"
            "import app.framework\n"
            "for m in pkgutil.walk_packages(app.framework.__path__, 'app.framework.'):\n"
            "    importlib.import_module(m.name)\n"
            "import app.core.security\n"
            "from app.framework.runtime import registry, FrameworkRuntimeError\n"
            "try:\n"
            "    registry.resolve('current_user')\n"
            "except FrameworkRuntimeError:\n"
            "    pass\n"
            "else:\n"
            "    raise AssertionError('未注册依赖应显式抛 FrameworkRuntimeError')\n"
            "print('INDEPENDENT-OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=BACKEND_ROOT,
            env={**os.environ, "SECRET_ENCRYPTION_KEY": "independence-probe-key"},
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"框架独立性验证失败:\nstdout: {result.stdout}\nstderr: {result.stderr[-2000:]}",
        )
        self.assertIn("INDEPENDENT-OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
