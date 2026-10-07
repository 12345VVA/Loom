"""WorkflowMemoryService 写路径单测（设计 §5.3 三级判定 / §4.2 并发防重 / §4.4 生命周期）。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_memory.py -q
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.core.config import settings
from app.modules.workflow.model.workflow import WorkflowDefinition
from app.modules.workflow.model.workflow_memory import WorkflowMemory
from app.modules.workflow.service import workflow_memory_service as wms
from app.modules.workflow.service.workflow_memory_service import (
    cascade_soft_delete_by_definition,
    content_hash_of,
    derive_memory_env,
    normalize_for_hash,
    sweep_memory_tombstones,
    upsert_memory,
)


def _upsert(session, definition_id: int = 1, memory_key: str | None = None, content: str = "c", **kw):
    """upsert_memory 缺省参数驱动（测试只关注变化项）。"""
    defaults = dict(
        memory_env="production",
        content=content,
        memory_key=memory_key,
        memory_type="fact",
        tags=[],
        embedding=None,
        embedding_space=None,
        source_instance_id=100,
        source_node_id="n1",
        source_run_type="production",
        user_id=7,
    )
    defaults.update(kw)
    return upsert_memory(session, definition_id=definition_id, **defaults)


class MemoryHelpersTestCase(unittest.TestCase):
    def test_normalize_for_hash(self):
        self.assertEqual(normalize_for_hash("  abc\r\n"), "abc")
        self.assertEqual(normalize_for_hash("a\r\nb\rc"), "a\nb\nc")
        # 规范化只用于 hash，不改变原文

    def test_content_hash_stable_across_whitespace(self):
        self.assertEqual(content_hash_of("abc"), content_hash_of(" abc \r\n"))

    def test_derive_memory_env(self):
        self.assertEqual(derive_memory_env("production"), "production")
        self.assertEqual(derive_memory_env("trial"), "production")  # trial 有意写生产
        self.assertEqual(derive_memory_env("test_node"), "test")


class UpsertKeyTestCase(unittest.TestCase):
    """一级判定：key upsert。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_created_then_updated_preserves_creator(self):
        mid1, action1 = _upsert(self.session, memory_key="k1", content="v1", user_id=7)
        self.assertEqual(action1, "created")
        mid2, action2 = _upsert(self.session, memory_key="k1", content="v2", user_id=9)
        self.assertEqual((mid2, action2), (mid1, "updated"))
        row = self.session.get(WorkflowMemory, mid1)
        # created_by / created_at 恒不变；updated_by 刷新为当次操作者
        self.assertEqual(row.created_by_user_id, 7)
        self.assertEqual(row.updated_by_user_id, 9)
        self.assertEqual(row.content, "v2")

    def test_key_upsert_refreshes_source_provenance(self):
        mid1, _ = _upsert(self.session, memory_key="k1", source_instance_id=100, source_run_type="production")
        mid2, action = _upsert(
            self.session, memory_key="k1", content="v2", source_instance_id=200, source_run_type="trial", user_id=9
        )
        self.assertEqual(action, "updated")
        row = self.session.get(WorkflowMemory, mid2)
        # source_* 语义 =「当前这条 content 是哪次运行写的」，随 upsert 刷新
        self.assertEqual(row.source_instance_id, 200)
        self.assertEqual(row.source_run_type, "trial")

    def test_key_upsert_recomputes_embedding(self):
        mid, _ = _upsert(self.session, memory_key="k1", embedding=[0.1, 0.2], embedding_space="m1:2", content="v1")
        mid2, _ = _upsert(self.session, memory_key="k1", content="v2", embedding=[0.3, 0.4], embedding_space="m1:2")
        row = self.session.get(WorkflowMemory, mid2)
        self.assertEqual(json.loads(row.embedding), [0.3, 0.4])
        self.assertEqual(row.embedding_space, "m1:2")

    def test_embedding_failure_overwrites_old_vector(self):
        """embedding 失败（vector=None + 裸 code）覆盖旧 ready 向量：content 已变，旧向量失真。"""
        mid, _ = _upsert(self.session, memory_key="k1", embedding=[0.1], embedding_space="m1:1")
        _upsert(self.session, memory_key="k1", content="v2", embedding=None, embedding_space="m1")
        row = self.session.get(WorkflowMemory, mid)
        self.assertIsNone(row.embedding)
        self.assertEqual(row.embedding_space, "m1")  # 裸 code 失败态


class UpsertHashTestCase(unittest.TestCase):
    """二级判定：无 key 行 hash 精确去重。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_deduplicated_returns_first_write_id(self):
        mid1, action1 = _upsert(self.session, content="abc")
        self.assertEqual(action1, "created")
        mid2, action2 = _upsert(self.session, content="abc")
        self.assertEqual((mid2, action2), (mid1, "deduplicated"))
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(rows), 1)

    def test_normalized_whitespace_dedup_keeps_first_content(self):
        """规范化判同（首尾空白/换行差异）→ 首写为准，后写丢弃，content 保持首写原样。"""
        mid1, _ = _upsert(self.session, content="abc")
        mid2, action = _upsert(self.session, content="abc\n")
        self.assertEqual(action, "deduplicated")
        self.assertEqual(mid2, mid1)
        row = self.session.get(WorkflowMemory, mid1)
        self.assertEqual(row.content, "abc")  # 落库以首写为准

    def test_key_and_hash_are_orthogonal(self):
        """key=A 与 key=B 同 content 共存（key 行唯一性由 key 承担，不撞 hash 索引）。"""
        _upsert(self.session, memory_key="A", content="same")
        _upsert(self.session, memory_key="B", content="same")
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(rows), 2)

    def test_key_upsert_to_existing_keyless_content_no_violation(self):
        """key 行 upsert 更新至与某无 key 行同 content：不违约（hash 唯一仅限无 key 行）。"""
        _upsert(self.session, content="shared")
        _upsert(self.session, memory_key="K", content="other")
        _, action = _upsert(self.session, memory_key="K", content="shared")
        self.assertEqual(action, "updated")


class IsolationTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_env_isolation(self):
        """test 行与生产行互不干扰：同 key 同 hash 各自独立，唯一索引按 env 分域。"""
        _upsert(self.session, memory_key="k", content="prod-v")
        test_mid, test_action = _upsert(self.session, memory_key="k", content="prod-v", memory_env="test")
        self.assertEqual(test_action, "created")  # test env 首写，不撞生产
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(rows), 2)

    def test_cross_definition_isolation(self):
        """跨工作流物理隔离：同 key 共存于不同 definition（B 永远看不到 A 的记忆）。"""
        _upsert(self.session, definition_id=1, memory_key="k", content="a-flow")
        mid_b, action_b = _upsert(self.session, definition_id=2, memory_key="k", content="b-flow")
        self.assertEqual(action_b, "created")
        self.assertNotEqual(mid_b, 0)

    def test_invalid_memory_type_rejected(self):
        with self.assertRaises(ValueError):
            _upsert(self.session, memory_type="unknown")

    def test_oversize_content_rejected(self):
        with self.assertRaises(ValueError):
            _upsert(self.session, content="x" * (settings.WORKFLOW_MEMORY_MAX_CONTENT_LENGTH + 1))


class ConcurrentWindowTestCase(unittest.TestCase):
    """并发窗口（设计 §4.2 v5.1）：快路径 SELECT miss → INSERT 撞唯一索引 → 重走判定。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _with_fast_path_miss(self):
        """快路径第一次返回 None（模拟并发方尚未提交时已执行 SELECT），慢路径走真实查询。"""
        real_find = wms._find_existing
        calls = {"n": 0}

        def fake_find(session, definition_id, memory_env, memory_key, content_hash):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_find(session, definition_id, memory_env, memory_key, content_hash)

        return patch.object(wms, "_find_existing", fake_find)

    def test_concurrent_same_key_last_writer_wins(self):
        """并发同 key 不同 content：撞 uq_mem_key 重走判定进 UPDATE，后写者 content 胜出。"""
        _upsert(self.session, memory_key="k", content="v1")
        with self._with_fast_path_miss():
            mid, action = _upsert(self.session, memory_key="k", content="v2", user_id=9)
        self.assertEqual(action, "updated")
        row = self.session.get(WorkflowMemory, mid)
        self.assertEqual(row.content, "v2")  # 不静默丢弃后写者
        self.assertEqual(row.updated_by_user_id, 9)

    def test_concurrent_same_content_no_key_deduplicated(self):
        """并发同 content 无 key：撞 uq_mem_hash，恰好一行，另一调用 deduplicated。"""
        _upsert(self.session, content="dup")
        with self._with_fast_path_miss():
            mid, action = _upsert(self.session, content="dup")
        self.assertEqual(action, "deduplicated")
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(rows), 1)


class SemanticWarningTestCase(unittest.TestCase):
    """三级判定：语义相似仅 warning 不丢弃。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_similar_memory_kept_with_warning(self):
        """0.96 相似仍两行并存（8 折 vs 7 折不可按相似丢弃）+ warning 日志。"""
        vec = [1.0, 0.0]
        similar = [0.96, 0.28]  # 与 vec 余弦 ≈ 0.96
        _upsert(self.session, content="8折", embedding=vec, embedding_space="m:2")
        with self.assertLogs(wms.logger, level="WARNING"):
            mid, action = _upsert(self.session, content="7折", embedding=similar, embedding_space="m:2")
        self.assertEqual(action, "created")
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(rows), 2)

    def test_window_without_ready_rows_zero_cost_skip(self):
        """窗口内无 ready 行：跳过第 3 级，零开销退出（不产生 warning）。"""
        _upsert(self.session, content="admin 无向量")  # embedding=None，非 ready
        import logging

        records = []
        handler = logging.Handler()
        handler.emit = records.append
        wms.logger.addHandler(handler)
        try:
            _upsert(self.session, content="新记忆", embedding=[1.0, 0.0], embedding_space="m:2")
        finally:
            wms.logger.removeHandler(handler)
        self.assertEqual([r for r in records if r.levelno >= logging.WARNING], [])

    def test_warning_only_when_space_matches(self):
        """space 不一致（不同模型/维度）不比对（余弦要求同空间）。"""
        _upsert(self.session, content="旧模型", embedding=[1.0, 0.0], embedding_space="old:2")
        import logging

        records = []
        handler = logging.Handler()
        handler.emit = records.append
        wms.logger.addHandler(handler)
        try:
            _upsert(self.session, content="新模型", embedding=[1.0, 0.0], embedding_space="new:2")
        finally:
            wms.logger.removeHandler(handler)
        self.assertEqual([r for r in records if r.levelno >= logging.WARNING], [])


class ScopeCapTestCase(unittest.TestCase):
    """容量保护（设计 §4.4）：先插后淘、COALESCE 排序、软删入墓碑。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_cap_evicts_oldest_by_coalesce_order(self):
        with (
            patch.object(settings, "WORKFLOW_MEMORY_SCOPE_CAP", 3),
            patch.object(settings, "WORKFLOW_MEMORY_EVICTION_BATCH", 2),
        ):
            m1, _ = _upsert(self.session, memory_key="k1", content="oldest")
            _upsert(self.session, memory_key="k2", content="mid")
            _upsert(self.session, memory_key="k3", content="newest")
            # 第 4 条触发超限（active=4 > 3），淘 COALESCE 最旧 2 条
            m4, action4 = _upsert(self.session, memory_key="k4", content="newest2")
        self.assertEqual(action4, "created")  # 先插后淘：新行先落
        active = list(
            self.session.exec(
                select(WorkflowMemory).where(WorkflowMemory.delete_time.is_(None))  # type: ignore[attr-defined]
            ).all()
        )
        active_ids = {r.id for r in active}
        self.assertIn(m4, active_ids)  # 新行不被淘
        self.assertNotIn(m1, active_ids)  # 最旧被淘
        tombstones = list(
            self.session.exec(
                select(WorkflowMemory).where(WorkflowMemory.delete_time.is_not(None))  # type: ignore[attr-defined]
            ).all()
        )
        self.assertEqual(len(tombstones), 2)  # 软删入墓碑（淘汰批量 2）

    def test_recently_updated_old_memory_survives(self):
        """刚 update 的老记忆 updated_at 刷新（before_update 事件），COALESCE 排序下不被淘。

        事件语义（database.py）：ORM 属性真实变更才触发 UPDATE 并刷新 updated_at，
        手动赋值会被事件覆盖；Core 层 UPDATE 不触发事件（version_service 先例）——
        k2 经 Core UPDATE 显式置旧，k1 走 key upsert（user_id 变化 → 真实 UPDATE）。
        """
        m1, _ = _upsert(self.session, memory_key="k1", content="old-but-refreshed", user_id=7)
        _upsert(self.session, memory_key="k2", content="mid")
        _upsert(self.session, memory_key="k1", content="old-but-refreshed", user_id=9)  # 真实 UPDATE → updated_at 刷新
        from sqlalchemy import update as sa_update

        self.session.execute(
            sa_update(WorkflowMemory)
            .where(WorkflowMemory.memory_key == "k2")
            .values(updated_at=datetime.now(UTC) - timedelta(hours=2))
        )
        self.session.commit()
        with (
            patch.object(settings, "WORKFLOW_MEMORY_SCOPE_CAP", 2),
            patch.object(settings, "WORKFLOW_MEMORY_EVICTION_BATCH", 1),
        ):
            _upsert(self.session, memory_key="k3", content="newest")  # 超限（active=3 > 2），淘 1 条
        row = self.session.get(WorkflowMemory, m1)
        self.assertIsNone(row.delete_time)  # 刚 update 的不被淘
        evicted = [r for r in self.session.exec(select(WorkflowMemory)).all() if r.delete_time is not None]
        self.assertEqual(len(evicted), 1)
        self.assertEqual(evicted[0].memory_key, "k2")


class LifecycleTestCase(unittest.TestCase):
    """definition 级联软删 + 墓碑硬清。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_cascade_soft_delete_by_definition(self):
        self.session.add(WorkflowDefinition(code="wf1", name="WF1", is_active=True, user_id=1))
        self.session.commit()
        definition = self.session.exec(select(WorkflowDefinition)).first()
        _upsert(self.session, definition_id=definition.id, memory_key="k1")
        _upsert(self.session, definition_id=definition.id, memory_key="k2", memory_env="test")
        _upsert(self.session, definition_id=999, memory_key="k3")  # 别的工作流的，不动
        removed = cascade_soft_delete_by_definition(self.session, definition.id)
        self.assertEqual(removed, 2)
        remaining_active = list(
            self.session.exec(
                select(WorkflowMemory).where(
                    WorkflowMemory.definition_id == definition.id,
                    WorkflowMemory.delete_time.is_(None),  # type: ignore[attr-defined]
                )
            ).all()
        )
        self.assertEqual(remaining_active, [])

    def test_sweep_tombstones_only_expired(self):
        _upsert(self.session, memory_key="old")
        _upsert(self.session, memory_key="fresh")
        now = datetime.now(UTC)
        rows = list(self.session.exec(select(WorkflowMemory)).all())
        rows[0].delete_time = now - timedelta(days=91)  # 过期
        rows[1].delete_time = now - timedelta(days=1)  # 未过期
        self.session.add(rows[0])
        self.session.add(rows[1])
        self.session.commit()
        removed = sweep_memory_tombstones(keep_days=90, session=self.session)
        self.assertEqual(removed, 1)
        survived = list(self.session.exec(select(WorkflowMemory)).all())
        self.assertEqual(len(survived), 1)
        self.assertEqual(survived[0].memory_key, "fresh")


class AdminAddTestCase(unittest.TestCase):
    """管理页 add：admin 溯源 + 审计 + embedding 三态。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _service(self):
        from app.modules.workflow.service.workflow_memory_service import WorkflowMemoryService

        return WorkflowMemoryService(self.session)

    def test_add_records_admin_provenance_and_audit(self):
        payload = {
            "definition_id": 1,
            "content": "手工新增的记忆",
            "memory_type": "fact",
            "memory_key": "manual",
            "tags": ["ops"],
        }
        svc = self._service()
        from app.modules.base.model.auth import User

        admin = User(id=42, username="admin42", full_name="admin", password_hash="x", is_active=True)
        entity = svc.add(payload, current_user=admin)
        row = self.session.get(WorkflowMemory, entity.id)
        self.assertEqual(row.source_run_type, "admin")
        self.assertEqual(row.memory_env, "production")
        self.assertEqual(row.created_by_user_id, 42)
        self.assertEqual(row.updated_by_user_id, 42)
        self.assertEqual(row.content_hash, content_hash_of("手工新增的记忆"))
        self.assertEqual(json.loads(row.tags), ["ops"])
        self.assertIsNone(row.embedding)  # 未配 profile → 未配置态

    def test_add_embedding_states(self):
        from app.modules.base.model.auth import User

        admin = User(id=42, username="admin42", full_name="admin", password_hash="x", is_active=True)
        # ready 态
        with patch.object(wms, "run_ai_embedding", return_value=([0.1, 0.2], "m:2")):
            e1 = self._service().add(
                {"definition_id": 1, "content": "a", "embedding_profile_code": "p1"}, current_user=admin
            )
        row1 = self.session.get(WorkflowMemory, e1.id)
        self.assertEqual(json.loads(row1.embedding), [0.1, 0.2])
        self.assertEqual(row1.embedding_space, "m:2")
        # 失败态：裸 code
        with patch.object(wms, "run_ai_embedding", return_value=(None, "m")):
            e2 = self._service().add(
                {"definition_id": 1, "content": "b", "embedding_profile_code": "p1"}, current_user=admin
            )
        row2 = self.session.get(WorkflowMemory, e2.id)
        self.assertIsNone(row2.embedding)
        self.assertEqual(row2.embedding_space, "m")
        # 未配置态：不填 profile → NULL
        e3 = self._service().add({"definition_id": 1, "content": "c"}, current_user=admin)
        row3 = self.session.get(WorkflowMemory, e3.id)
        self.assertIsNone(row3.embedding)
        self.assertIsNone(row3.embedding_space)

    def test_add_ignores_direct_embedding_injection(self):
        """不接受请求直塞 embedding 向量（管理页 add 只经 profile 计算；DTO 层已丢弃
        额外字段，service 层 _before_add pop 双保险）——落库恒 NULL 未配置态。"""
        payload = {"definition_id": 1, "content": "x", "embedding": "[1,2,3]"}
        svc = self._service()
        entity = svc.add(payload)
        row = self.session.get(WorkflowMemory, entity.id)
        self.assertIsNone(row.embedding)


if __name__ == "__main__":
    unittest.main()
