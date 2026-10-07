"""节点元数据 manifest 单一来源一致性测试（三期B7 / WF-P2-7，原 P1-3 防漂移守卫升级）。

后端（注册表 + graph_validate 常量集）是唯一权威；前端产物
frontend/src/modules/workflow/generated/node-manifest.ts 由
scripts/dump_node_manifest.py 生成。本测试比对产物与后端权威：
注册表或常量集改动而未重新生成时在此显式失败（CI 亦可跑
dump_node_manifest.py --check 达到同等效果）。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import app.modules.workflow.service.node_executors  # noqa: F401  import 副作用完成注册
from app.modules.workflow.service.graph_validate import (
    CONDITIONAL_NODE_TYPES,
    INTERRUPT_NODE_TYPES,
    MOCK_TOOL_CODES,
    SUBGRAPH_NODE_TYPES,
    UNTESTABLE_NODE_TYPES,
)
from app.modules.workflow.service.node_schema import NODE_OUTPUT_VAR_DEFAULTS
from app.modules.workflow.service.state import node_registry

BACKEND_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_MANIFEST = BACKEND_ROOT.parent / "frontend" / "src" / "modules" / "workflow" / "generated" / "node-manifest.ts"


def _load_manifest_source() -> str:
    assert FRONTEND_MANIFEST.exists(), (
        f"前端 manifest 产物不存在: {FRONTEND_MANIFEST}。请运行 python scripts/dump_node_manifest.py 生成。"
    )
    return FRONTEND_MANIFEST.read_text(encoding="utf-8")


def _parse_node_manifest(source: str) -> dict[str, dict[str, bool | str | None]]:
    """从产物解析 NODE_MANIFEST 数组（一行一条 entry 的固定生成格式）。"""
    match = re.search(r"NODE_MANIFEST[^=]*=\s*\[(.*?)\] as const", source, re.S)
    assert match, "产物中未找到 NODE_MANIFEST 数组"
    entries: dict[str, dict[str, bool | str | None]] = {}
    for m in re.finditer(
        r"type:\s*'([a-z_]+)',\s*untestable:\s*(true|false),\s*interrupt:\s*(true|false),"
        r"\s*subgraph:\s*(true|false),\s*conditional:\s*(true|false),"
        r"\s*idempotent:\s*(true|false),\s*deprecated:\s*(true|false),"
        r"\s*outputVarDefault:\s*(null|'[a-z_]+')",
        match.group(1),
    ):
        ovd = None if m.group(8) == "null" else m.group(8).strip("'")
        entries[m.group(1)] = {
            "untestable": m.group(2) == "true",
            "interrupt": m.group(3) == "true",
            "subgraph": m.group(4) == "true",
            "conditional": m.group(5) == "true",
            "idempotent": m.group(6) == "true",
            "deprecated": m.group(7) == "true",
            "outputVarDefault": ovd,
        }
    return entries


def _parse_str_array(source: str, name: str) -> set[str]:
    match = re.search(rf"{name}[^=]*=\s*\[([^\]]*)\]", source)
    assert match, f"产物中未找到 {name} 数组"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


class NodeManifestSyncTestCase(unittest.TestCase):
    """NODE_MANIFEST 产物与后端注册表/常量集逐字段比对。"""

    @classmethod
    def setUpClass(cls):
        cls.source = _load_manifest_source()
        cls.manifest = _parse_node_manifest(cls.source)

    def test_manifest_covers_all_registered_types(self):
        self.assertEqual(
            set(self.manifest.keys()),
            set(node_registry.types()),
            "NODE_MANIFEST 与后端注册表节点类型不一致：请重新运行 python scripts/dump_node_manifest.py",
        )

    def test_manifest_flags_match_backend(self):
        for node_type, entry in self.manifest.items():
            with self.subTest(node_type=node_type):
                self.assertEqual(entry["untestable"], node_type in UNTESTABLE_NODE_TYPES, node_type)
                self.assertEqual(entry["interrupt"], node_type in INTERRUPT_NODE_TYPES, node_type)
                self.assertEqual(entry["subgraph"], node_type in SUBGRAPH_NODE_TYPES, node_type)
                self.assertEqual(entry["conditional"], node_type in CONDITIONAL_NODE_TYPES, node_type)
                self.assertEqual(entry["idempotent"], node_registry.is_idempotent(node_type), node_type)
                self.assertEqual(entry["deprecated"], node_registry.is_deprecated(node_type), node_type)
                self.assertEqual(
                    entry["outputVarDefault"],
                    NODE_OUTPUT_VAR_DEFAULTS.get(node_type),
                    node_type,
                )

    def test_output_var_defaults_match_executor_runtime(self):
        """权威表与执行器运行时 config.get 默认值一致（WF-P2-8 防再漂移）。"""
        import inspect
        import re as _re

        import app.modules.workflow.service.node_executors as ne

        executor_of = {
            "llm": ne.execute_llm_node,
            "human_input": ne.execute_human_input_node,
            "loop_controller": ne.execute_loop_controller_node,
            "batch_processor": ne.execute_batch_processor_node,
            "image_generator": ne.execute_image_generator_node,
            "tool_executor": ne.execute_tool_executor_node,
            "variable_transform": ne.execute_variable_transform_node,
        }
        for node_type, fn in executor_of.items():
            defaults = _re.findall(r'config\.get\("output_variable",\s*"([a-z_]+)"\)', inspect.getsource(fn))
            with self.subTest(node_type=node_type):
                self.assertTrue(defaults, f"{node_type} 执行器源码中未找到 output_variable 默认值")
                self.assertEqual(
                    NODE_OUTPUT_VAR_DEFAULTS[node_type],
                    defaults[0],
                    f"{node_type} 的 NODE_OUTPUT_VAR_DEFAULTS 与执行器运行时默认值漂移",
                )

    def test_derived_constant_arrays_match_backend(self):
        for name, backend_set in (
            ("UNTESTABLE_NODE_TYPES", UNTESTABLE_NODE_TYPES),
            ("INTERRUPT_NODE_TYPES", INTERRUPT_NODE_TYPES),
            ("SUBGRAPH_NODE_TYPES", SUBGRAPH_NODE_TYPES),
            ("CONDITIONAL_NODE_TYPES", CONDITIONAL_NODE_TYPES),
            ("MOCK_TOOL_CODES", MOCK_TOOL_CODES),
        ):
            with self.subTest(array=name):
                self.assertEqual(
                    _parse_str_array(self.source, name),
                    set(backend_set),
                    f"{name} 产物与后端不一致：请重新运行 python scripts/dump_node_manifest.py",
                )

    def test_backend_set_covers_interrupt_types(self):
        """中断类节点（依赖人工交互）必须不可单节点测试——子集关系守护。"""
        self.assertTrue(
            INTERRUPT_NODE_TYPES <= UNTESTABLE_NODE_TYPES,
            "INTERRUPT_NODE_TYPES 中出现可单测节点：中断节点无法脱离 checkpointer 单独执行",
        )


class FrontendConstantsReExportTestCase(unittest.TestCase):
    """constants.ts 保留 re-export：消费方（base-node/node-config-panel）零改动。"""

    def test_constants_re_exports_manifest_symbols(self):
        constants_path = (
            BACKEND_ROOT.parent / "frontend" / "src" / "modules" / "workflow" / "components" / "constants.ts"
        )
        source = constants_path.read_text(encoding="utf-8")
        self.assertIn(
            "export { UNTESTABLE_NODE_TYPES, MOCK_TOOL_CODES } from '../generated/node-manifest'",
            source,
            "constants.ts 缺少 manifest 派生 re-export——消费方将拿到旧镜像或编译失败",
        )


if __name__ == "__main__":
    unittest.main()
