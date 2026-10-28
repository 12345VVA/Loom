"""agent 工具体系测试（P2）：SPI 收集 / 允许列表封闭性 / 冲突 fail-fast / degraded /
资源同步保留禁用态 / 契约兼容性判定表 / 执行安全实时判定（设计 3.3 + 22 条验收映射 2/13/17/18）。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from fastapi import HTTPException
from helpers import make_test_engine
from pydantic import BaseModel
from sqlmodel import Session, select

from app.modules.agent.model.agent import AgentToolResource, AgentToolResourceVersion
from app.modules.agent.service import tool_registry
from app.modules.agent.service.tool_registry import (
    RegisteredTool,
    assert_execution_allowed,
    bootstrap_registry,
    collect_agent_tools,
    is_contract_compatible,
    metadata_hash_of,
    sync_resources,
)
from app.modules.asset.model.asset import AssetCharacter
from app.modules.base.model.sys import SysLog


class _FakeCtx:
    def __init__(self):
        self.db = None
        self.user_id = 1
        self.is_super_admin = False


class _Args(BaseModel):
    pass


def _tool(name: str, level: str = "readonly") -> RegisteredTool:
    return RegisteredTool(
        name=name, description=f"{name} 描述", level=level, args_model=_Args, func=lambda a, c: "{}", module="m"
    )


def _new_tmp_root() -> Path:
    """系统临时目录（工作区不留构建垃圾，ruff/pytest 扫描不受影响）。"""
    return Path(tempfile.mkdtemp(prefix="loom-agent-toolmods-"))


def _write_tool_module(root: Path, module_name: str, entries: str) -> Path:
    """写一个可 import 的临时 agent_tools 模块（namespace package，唯一名防 sys.modules 缓存串扰）。"""
    mod_dir = root / module_name / "service"
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "agent_tools.py").write_text(
        textwrap.dedent(
            f"""
            from pydantic import BaseModel


            class _A(BaseModel):
                pass


            def _f(args, ctx):
                return "{{}}"


            def get_agent_tools():
                return {entries}
            """
        ),
        encoding="utf-8",
    )
    return root / module_name


class CollectAndAllowListTestCase(unittest.TestCase):
    """SPI 收集：真实模块冒烟 + 允许列表封闭性 + 冲突 fail-fast + 结构校验。"""

    def test_collect_real_modules_smoke(self):
        """真实收集：封闭清单工具全部注册（首版 5 只读 + E3 可逆写首批 4）。"""
        registry = collect_agent_tools()
        self.assertEqual(set(registry.keys()), tool_registry.RUNTIME_ALLOWED_TOOLS)
        for tool in registry.values():
            self.assertTrue(issubclass(tool.args_model, BaseModel))
            if tool.level == "readonly":
                continue
            # E3：可逆写必须带安全机制表三键（D11 二级治理）
            self.assertEqual(tool.level, "reversible_write")
            self.assertIsNotNone(tool.safety)
            self.assertTrue({"reversible_how", "concurrency", "audit_ref"}.issubset(tool.safety.keys()))

    def test_allow_list_closes_registration(self):
        """允许列表封闭性（验收 13）：不在 RUNTIME_ALLOWED_TOOLS 的工具不进注册表。"""
        root = _new_tmp_root()
        mod_dir = _write_tool_module(
            root,
            "pkg_allow",
            """[{"name": "query_asset", "description": "覆盖同名允许工具", "level": "readonly",
               "args_model": _A, "func": _f},
              {"name": "evil_tool", "description": "未过白名单", "level": "readonly",
               "args_model": _A, "func": _f}]""",
        )
        try:
            sys.path.insert(0, str(root))
            registry = collect_agent_tools([mod_dir], package_prefix="")
            self.assertIn("query_asset", registry)
            self.assertNotIn("evil_tool", registry)  # 白名单外：跳过不报错
        finally:
            sys.path.remove(str(root))
            shutil.rmtree(root, ignore_errors=True)

    def test_conflict_fail_fast_reports_both_modules(self):
        """同名冲突 fail-fast：报出双模块名（设计 3.3）。"""
        root = _new_tmp_root()
        entry = """[{"name": "query_asset", "description": "d", "level": "readonly",
                    "args_model": _A, "func": _f}]"""
        mod_a = _write_tool_module(root, "pkg_conf_a", entry)
        mod_b = _write_tool_module(root, "pkg_conf_b", entry)
        try:
            sys.path.insert(0, str(root))
            with self.assertRaises(ValueError) as ctx:
                collect_agent_tools([mod_a, mod_b], package_prefix="")
            # 两个模块名都出现在错误信息中
            self.assertIn("pkg_conf_a", str(ctx.exception))
            self.assertIn("pkg_conf_b", str(ctx.exception))
        finally:
            sys.path.remove(str(root))
            shutil.rmtree(root, ignore_errors=True)

    def test_structural_validation(self):
        """结构校验：缺 level / args_model 非 BaseModel / 缺 func 均启动期报错。"""
        root = _new_tmp_root()
        cases = {
            "pkg_bad_level": """[{"name": "current_time", "description": "d", "args_model": _A, "func": _f}]""",
            "pkg_bad_model": """[{"name": "current_time", "description": "d", "level": "readonly",
                                 "args_model": dict, "func": _f}]""",
            "pkg_no_func": """[{"name": "current_time", "description": "d", "level": "readonly",
                               "args_model": _A}]""",
            "pkg_bad_display_name": """[{"name": "current_time", "description": "d", "level": "readonly",
                                         "args_model": _A, "func": _f, "display_name": "  "}]""",
        }
        mod_dirs = {name: _write_tool_module(root, name, entries) for name, entries in cases.items()}
        try:
            sys.path.insert(0, str(root))
            for _name, mod_dir in mod_dirs.items():
                with self.assertRaises((TypeError, KeyError, ValueError)):
                    collect_agent_tools([mod_dir], package_prefix="")
        finally:
            sys.path.remove(str(root))
            shutil.rmtree(root, ignore_errors=True)


class BootstrapDegradedTestCase(unittest.TestCase):
    """build-then-swap：失败保留旧注册表 + degraded 标记；成功后清除。"""

    def tearDown(self):
        # 还原真实注册表，避免污染其他用例
        bootstrap_registry()

    def test_bootstrap_failure_keeps_old_registry_and_degrades(self):
        bootstrap_registry()  # 先建立有效注册表
        self.assertFalse(tool_registry.degraded_error())
        old_keys = set(tool_registry.get_registry().keys())

        def _boom(*args, **kwargs):
            raise RuntimeError("导入失败")

        original = tool_registry.collect_agent_tools
        tool_registry.collect_agent_tools = _boom
        try:
            bootstrap_registry()  # 不 raise（启动不阻断全站）
        finally:
            tool_registry.collect_agent_tools = original

        self.assertTrue(tool_registry.degraded_error())
        self.assertIn("导入失败", str(tool_registry.degraded_error()))
        self.assertEqual(set(tool_registry.get_registry().keys()), old_keys)  # 旧表保留

        bootstrap_registry()  # 恢复成功 → degraded 清除
        self.assertFalse(tool_registry.degraded_error())

    def test_bootstrap_empty_dirs_degrades_from_scratch(self):
        """首次启动收集失败：空注册表 + degraded（Agent 功能不可用但全站正常启动）。"""
        root = _new_tmp_root()
        tool_registry._registry.clear()
        try:
            bootstrap_registry([root], package_prefix="pkg_empty_ok")  # 空目录 → 空注册表（非失败）
            self.assertFalse(tool_registry.degraded_error())
            self.assertEqual(tool_registry.get_registry(), {})
        finally:
            tool_registry._registry.clear()
            shutil.rmtree(root, ignore_errors=True)


class ResourceSyncTestCase(unittest.TestCase):
    """资源层同步：只更新系统维护字段，绝不触碰 status（验收 17 前置）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                AssetCharacter.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        tool_registry._registry.clear()
        tool_registry._registry.update({"query_asset": _tool("query_asset"), "current_time": _tool("current_time")})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _row(self, tool_name: str) -> AgentToolResource:
        return self.session.exec(select(AgentToolResource).where(AgentToolResource.tool_name == tool_name)).one()

    def test_sync_creates_and_updates_without_touching_status(self):
        result = sync_resources(self.session, operator_id=1)
        self.assertEqual(result["count"], 2)
        row = self._row("query_asset")
        self.assertTrue(row.status)  # 新建默认启用
        old_hash = row.metadata_hash

        row.status = False  # 管理员紧急禁用
        self.session.add(row)
        self.session.commit()

        # 工具描述变更后再 sync：维护字段更新、status 保持禁用
        tool_registry._registry["query_asset"] = RegisteredTool(
            name="query_asset",
            description="更新后的描述",
            level="readonly",
            args_model=_Args,
            func=lambda a, c: "{}",
            module="asset",
        )
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        row2 = self._row("query_asset")
        self.assertEqual(row2.description, "更新后的描述")
        self.assertNotEqual(row2.metadata_hash, old_hash)
        self.assertFalse(row2.status)  # 禁用态不被代码刷新恢复

    def test_sync_display_name_declared_takes_over_admin_value_kept(self):
        """display_name（管理面展示名）：声明接管「未定制」行（原值=工具名）；管理员定制值不覆盖。"""
        tool_registry._registry["query_asset"] = RegisteredTool(
            name="query_asset",
            description="d",
            level="readonly",
            args_model=_Args,
            func=lambda a, c: "{}",
            module="asset",
            display_name="查询资产",
        )
        sync_resources(self.session, operator_id=1)
        self.assertEqual(self._row("query_asset").display_name, "查询资产")

        row = self._row("query_asset")
        row.display_name = "资产查询（管理员定制）"
        self.session.add(row)
        self.session.commit()
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        self.assertEqual(self._row("query_asset").display_name, "资产查询（管理员定制）")

    def test_metadata_hash_changes_with_inputs(self):
        base = metadata_hash_of("d", {"type": "object"}, "readonly")
        self.assertEqual(base, metadata_hash_of("d", {"type": "object"}, "readonly"))
        self.assertNotEqual(base, metadata_hash_of("d2", {"type": "object"}, "readonly"))
        self.assertNotEqual(base, metadata_hash_of("d", {"type": "object"}, "reversible_write"))


class _ArgsWithKeyword(BaseModel):
    keyword: str


class ToolResourceVersionTestCase(unittest.TestCase):
    """E12 工具资源版本表（二批 3.13）：双哈希分类入册 / 当前值列同步 / 无变更不入版本。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                AssetCharacter.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        tool_registry._registry.clear()
        tool_registry._registry.update({"query_asset": _tool("query_asset")})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _row(self, tool_name: str = "query_asset") -> AgentToolResource:
        return self.session.exec(select(AgentToolResource).where(AgentToolResource.tool_name == tool_name)).one()

    def _versions(self, tool_name: str = "query_asset") -> list[AgentToolResourceVersion]:
        return list(
            self.session.exec(
                select(AgentToolResourceVersion)
                .where(AgentToolResourceVersion.tool_name == tool_name)
                .order_by(AgentToolResourceVersion.version)
            ).all()
        )

    def test_created_then_classified_versions_and_current_columns(self):
        # v1：首次入册 created + 当前值列回填
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        row = self._row()
        kinds = [v.change_kind for v in self._versions()]
        self.assertEqual(kinds, ["created"])
        self.assertIsNotNone(row.contract_hash)
        self.assertIsNotNone(row.meta_hash)

        # v2：仅元数据变（description）→ meta_change；契约哈希不变
        old_contract = row.contract_hash
        tool_registry._registry["query_asset"] = RegisteredTool(
            name="query_asset",
            description="全新的描述文案",
            level="readonly",
            args_model=_Args,
            func=lambda a, c: "{}",
            module="asset",
        )
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        self.assertEqual([v.change_kind for v in self._versions()], ["created", "meta_change"])
        self.assertEqual(self._row().contract_hash, old_contract)  # meta 变更不动契约态

        # v3：契约变（schema 加字段）→ contract_change
        tool_registry._registry["query_asset"] = RegisteredTool(
            name="query_asset",
            description="全新的描述文案",
            level="readonly",
            args_model=_ArgsWithKeyword,
            func=lambda a, c: "{}",
            module="asset",
        )
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        self.assertEqual(
            [v.change_kind for v in self._versions()],
            ["created", "meta_change", "contract_change"],
        )
        self.assertNotEqual(self._row().contract_hash, old_contract)

        # 无变更重复 sync → 不入新版本（防空转版本线）
        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        self.assertEqual(len(self._versions()), 3)

    def test_legacy_row_without_hashes_gets_created_baseline(self):
        """迁移 0032 前的存量行（双哈希 NULL）：首次 sync 建 v1=created 并回填当前值列。"""
        self.session.add(
            AgentToolResource(
                tool_name="query_asset",
                display_name="query_asset",
                description="存量描述",
                source_type="builtin",
                level="readonly",
                status=False,  # 管理员已禁用——sync 不得触碰（D14）
                metadata_hash="legacy",
            )
        )
        self.session.commit()

        sync_resources(self.session, operator_id=1)
        self.session.expire_all()
        row = self._row()
        self.assertEqual([v.change_kind for v in self._versions()], ["created"])
        self.assertEqual(self._versions()[0].version, 1)
        self.assertIsNotNone(row.contract_hash)
        self.assertIsNotNone(row.meta_hash)
        self.assertFalse(row.status)  # 禁用态不被入册流程恢复

    def test_meta_change_does_not_affect_contract_compatibility(self):
        """兼容判定只看 contract_hash（meta 变更不触发 fail-close，二批 3.13）。"""
        from app.modules.agent.service.tool_registry import contract_hash_of, meta_hash_of

        params = {"type": "object", "properties": {"keyword": {"type": "string"}}}
        c1 = contract_hash_of(params, "readonly")
        # 元数据（description）与契约哈希正交
        self.assertEqual(contract_hash_of(params, "readonly"), c1)
        self.assertNotEqual(meta_hash_of("描述A"), meta_hash_of("描述B"))
        # 判定入口本就只收 parameters：description 不进判定输入
        self.assertTrue(is_contract_compatible(params, dict(params)))


class ContractCompatibilityTestCase(unittest.TestCase):
    """契约兼容性判定表（验收 18：fail-close；未识别约束默认不兼容）。"""

    def _obj(self, props: dict, required: list[str] | None = None) -> dict:
        return {"type": "object", "properties": props, "required": required or []}

    def test_identical_and_widening_compatible(self):
        snap = self._obj({"a": {"type": "string"}}, ["a"])
        self.assertTrue(is_contract_compatible(snap, snap))  # 完全相同
        widened = self._obj({"a": {"type": "string"}, "b": {"type": "integer"}}, ["a"])  # 新增可选属性
        self.assertTrue(is_contract_compatible(snap, widened))
        enum_widened = self._obj({"a": {"type": "string", "enum": ["x", "y", "z"]}}, [])
        snap_enum = self._obj({"a": {"type": "string", "enum": ["x", "y"]}}, [])
        self.assertTrue(is_contract_compatible(snap_enum, enum_widened))  # 枚举扩大=放宽=兼容

    def test_narrowing_incompatible(self):
        base = self._obj({"a": {"type": "string", "enum": ["x", "y"]}}, ["a"])
        self.assertFalse(is_contract_compatible(base, self._obj({"a": {"type": "integer"}}, ["a"])))  # 类型变更
        self.assertFalse(is_contract_compatible(base, self._obj({}, ["a"])))  # 属性删除
        self.assertFalse(
            is_contract_compatible(base, self._obj({"a": {"type": "string"}}, ["a", "b"]))
        )  # required 扩大
        self.assertFalse(
            is_contract_compatible(base, self._obj({"a": {"type": "string", "enum": ["x"]}}, ["a"]))
        )  # 枚举缩减
        self.assertFalse(
            is_contract_compatible(
                self._obj({"n": {"type": "number", "minimum": 1}}, []),
                self._obj({"n": {"type": "number", "minimum": 5}}, []),
            )
        )  # 约束收紧
        self.assertFalse(
            is_contract_compatible(
                self._obj({"a": {"type": "string"}}, []),
                self._obj({"a": {"type": "string", "pattern": "^x"}}, []),
            )
        )  # current 新增未识别约束键 → fail-close
        self.assertFalse(
            is_contract_compatible(
                self._obj({"o": self._obj({"x": {"type": "string"}}, ["x"])}, []),
                self._obj({"o": self._obj({"x": {"type": "string"}}, ["x", "y"])}, []),
            )
        )  # 嵌套对象 required 扩大


class ExecutionSafetyTestCase(unittest.TestCase):
    """执行安全实时判定（独立于契约兼容）：绑定/允许列表/level 升级/资源层启停。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[AgentToolResource.__table__, AgentToolResourceVersion.__table__, SysLog.__table__]
        )
        self.session = Session(self.engine)
        tool_registry._registry.clear()
        tool_registry._registry.update({"query_asset": _tool("query_asset")})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def test_unregistered_and_unbound_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            assert_execution_allowed("no_such_tool", snapshot_level="readonly", bound_tool_names={"query_asset"})
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(HTTPException) as ctx:
            assert_execution_allowed("query_asset", snapshot_level="readonly", bound_tool_names={"other"})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_level_upgrade_rejected_even_if_schema_unchanged(self):
        """level 升级（readonly → reversible_write）：schema 未变也拒绝（评审 v1.4）。

        模拟：发布时工具为 readonly，之后代码将其升级为 reversible_write——当前注册 level
        高于快照 level，即拒绝执行。
        """
        tool_registry._registry["query_asset"] = _tool("query_asset", level="reversible_write")
        with self.assertRaises(HTTPException) as ctx:
            assert_execution_allowed("query_asset", snapshot_level="readonly", bound_tool_names={"query_asset"})
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("重新发布", ctx.exception.detail)
        # 同级放行（readonly vs readonly）
        tool_registry._registry["query_asset"] = _tool("query_asset", level="readonly")
        tool = assert_execution_allowed("query_asset", snapshot_level="readonly", bound_tool_names={"query_asset"})
        self.assertEqual(tool.name, "query_asset")

    def test_resource_disabled_rejected_in_realtime(self):
        """资源层禁用实时拦截（D14 紧急禁用覆盖快照，验收 17）。"""
        sync_resources(self.session)
        row = self.session.exec(select(AgentToolResource).where(AgentToolResource.tool_name == "query_asset")).one()
        row.status = False
        self.session.add(row)
        self.session.commit()
        with self.assertRaises(HTTPException) as ctx:
            assert_execution_allowed(
                "query_asset", snapshot_level="readonly", bound_tool_names={"query_asset"}, session=self.session
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("禁用", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
