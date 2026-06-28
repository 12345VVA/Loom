"""M1 补索引机制测试：_ensure_indexes 的幂等性、SKIP_INDEX_ENSURE 开关、INDEX_DEFINITIONS 落地。

Field(index=True) 仅对 create_all 新建表生效；_ensure_indexes 为现有库补齐 created_at 等
查询关键索引（统计聚合/分页主路径）。本测试在独立内存 SQLite engine 上验证其行为。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from app.core import database as db_module
from app.core.database import INDEX_DEFINITIONS, _ensure_indexes


def _make_test_engine():
    """独立内存 SQLite engine（StaticPool 保证单连接，便于 inspect 一致性）。"""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


class EnsureIndexesTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = _make_test_engine()
        # 建立全部业务表（含 ai_model_call_log / workflow_execution_log / workflow_instance）
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _index_names(self, table: str) -> set[str]:
        return {ix["name"] for ix in inspect(self.engine).get_indexes(table) if ix.get("name")}

    def test_creates_missing_indexes(self):
        with patch.object(db_module, "engine", self.engine):
            _ensure_indexes()
        ai_names = self._index_names("ai_model_call_log")
        # created_at 单列 + 三个复合索引均建立（统计聚合主路径）
        self.assertIn("ix_ai_model_call_log_created_at", ai_names)
        self.assertIn("ix_ai_model_call_log_status_created_at", ai_names)
        self.assertIn("ix_ai_model_call_log_user_id_created_at", ai_names)
        self.assertIn("ix_ai_model_call_log_model_id_created_at", ai_names)
        # workflow 表的复合索引
        self.assertIn(
            "ix_workflow_execution_log_instance_id_created_at",
            self._index_names("workflow_execution_log"),
        )

    def test_idempotent(self):
        """连续两次调用不报错，索引不重复创建。"""
        with patch.object(db_module, "engine", self.engine):
            _ensure_indexes()
            _ensure_indexes()
        self.assertIn("ix_ai_model_call_log_created_at", self._index_names("ai_model_call_log"))

    def test_skip_flag_skips_creation(self):
        """SKIP_INDEX_ENSURE=True 时跳过补建。"""
        with patch.object(db_module.settings, "SKIP_INDEX_ENSURE", True), \
                patch.object(db_module, "engine", self.engine):
            _ensure_indexes()
        self.assertNotIn("ix_ai_model_call_log_created_at", self._index_names("ai_model_call_log"))

    def test_definitions_use_if_not_exists_pattern(self):
        """所有索引定义命名规范，列片段非空。"""
        for index_name, table_name, columns, _where in INDEX_DEFINITIONS:
            self.assertTrue(index_name.startswith(f"ix_{table_name}_"), index_name)
            self.assertTrue(columns.strip(), index_name)


if __name__ == "__main__":
    unittest.main()
