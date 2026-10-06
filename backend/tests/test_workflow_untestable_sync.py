"""UNTESTABLE_NODE_TYPES 前后端一致性测试（P1-3 防漂移）。

后端 graph_validate.py 是权威来源；前端 constants.ts 镜像一份用于提前禁用测试入口。
后端兜底 400 拦截 + 本测试跨栈比对真实源码：任一侧单方面改动会在此显式失败，
提醒同步另一侧（否则出现「前端放行、后端拒绝」或反向的入口漂移）。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.modules.workflow.service.graph_validate import UNTESTABLE_NODE_TYPES

BACKEND_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_CONSTANTS = BACKEND_ROOT.parent / "frontend" / "src" / "modules" / "workflow" / "components" / "constants.ts"


class UntestableNodeTypesSyncTestCase(unittest.TestCase):
    def test_backend_set_matches_frontend_mirror(self):
        """后端集合与前端镜像数组逐项一致（顺序无关）。"""
        self.assertTrue(FRONTEND_CONSTANTS.exists(), f"前端 constants 文件不存在: {FRONTEND_CONSTANTS}")
        source = FRONTEND_CONSTANTS.read_text(encoding="utf-8")
        match = re.search(r"UNTESTABLE_NODE_TYPES\s*=\s*\[([^\]]*)\]", source)
        self.assertIsNotNone(match, "前端 constants.ts 中未找到 UNTESTABLE_NODE_TYPES 数组")
        frontend_types = set(re.findall(r"'([a-z_]+)'", match.group(1)))
        self.assertEqual(
            frontend_types,
            set(UNTESTABLE_NODE_TYPES),
            "UNTESTABLE_NODE_TYPES 前后端不一致：请同步 graph_validate.py 与 constants.ts",
        )

    def test_backend_set_covers_interrupt_types(self):
        """中断类节点（依赖人工交互）必须不可单节点测试——子集关系守护。"""
        from app.modules.workflow.service.graph_validate import INTERRUPT_NODE_TYPES

        self.assertTrue(
            INTERRUPT_NODE_TYPES <= UNTESTABLE_NODE_TYPES,
            "INTERRUPT_NODE_TYPES 中出现可单测节点：中断节点无法脱离 checkpointer 单独执行",
        )


class MockToolCodesSyncTestCase(unittest.TestCase):
    """MOCK_TOOL_CODES 前后端一致性（WF-P0-2 防漂移）：后端拦截依据 / 前端 DEMO 徽标依据。"""

    def test_backend_set_matches_frontend_mirror(self):
        from app.modules.workflow.service.graph_validate import MOCK_TOOL_CODES

        self.assertTrue(FRONTEND_CONSTANTS.exists(), f"前端 constants 文件不存在: {FRONTEND_CONSTANTS}")
        source = FRONTEND_CONSTANTS.read_text(encoding="utf-8")
        match = re.search(r"MOCK_TOOL_CODES\s*=\s*\[([^\]]*)\]", source)
        self.assertIsNotNone(match, "前端 constants.ts 中未找到 MOCK_TOOL_CODES 数组")
        frontend_codes = set(re.findall(r"'([a-z_]+)'", match.group(1)))
        self.assertEqual(
            frontend_codes,
            set(MOCK_TOOL_CODES),
            "MOCK_TOOL_CODES 前后端不一致：请同步 graph_validate.py 与 constants.ts",
        )


if __name__ == "__main__":
    unittest.main()
