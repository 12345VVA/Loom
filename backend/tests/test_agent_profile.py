"""agent 发布快照体系测试（P4）：draft 同步重建 / 发布四步 / 幂等 / 窗口严格 / 回滚 /
并发发布不变量 / 对象级操作权（验收映射 7/14/15/21/22）。

并发发布竞态的真锁语义在 CI（PG，FOR UPDATE 行锁）验证（R3：本地 SQLite 退化整库锁）；
本地断言不变量：is_current 至多一条、版本线无重复、最终生效快照 = 最后提交内容。
"""

from __future__ import annotations

import unittest

from fastapi import HTTPException
from helpers import make_test_engine, seed_chat_channel
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_PUBLISH_ACTION_ROLLBACK,
    AGENT_STATUS_PUBLISHED,
    AgentProfile,
    AgentProfileCreateRequest,
    AgentProfileDraft,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
    AgentProfileUpdateRequest,
    AgentToolApproval,
    AgentToolResource,
    AgentToolResourceVersion,
)
from app.modules.agent.service.profile_service import (
    AgentProfileService,
)
from app.modules.agent.service.tool_registry import bootstrap_registry, sync_resources
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog

# E15：publish/run 校验依赖渠道窗口元数据，测试统一建最小渠道数据
_AI_CHANNEL_TABLES = [AiProvider.__table__, AiModel.__table__, AiModelProfile.__table__]


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin


class PublishProfileTestCase(unittest.TestCase):
    """发布/回滚/幂等/窗口/操作权（真注册表 + 资源层 current_time）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                *_AI_CHANNEL_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.service = AgentProfileService(self.session)
        bootstrap_registry()
        seed_chat_channel(self.engine)  # E15：deepseek-chat 窗口 32000
        sync_resources(self.session)  # 资源层记录（发布校验前置）
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.admin = _FakeUser(3, is_super_admin=True)
        self.profile = self._create()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _create(self, **kwargs) -> AgentProfile:
        payload = AgentProfileCreateRequest(
            name=kwargs.pop("name", "测试智能体"),
            model_profile_code="deepseek-chat",
            tools=kwargs.pop("tools", ["current_time"]),
            **kwargs,
        )
        return self.service.add(payload, current_user=self.owner)

    def _current(self, profile_id: int) -> AgentProfilePublishRecord | None:
        return self.session.exec(
            select(AgentProfilePublishRecord).where(
                AgentProfilePublishRecord.profile_id == profile_id,
                AgentProfilePublishRecord.is_current == True,  # noqa: E712
            )
        ).first()

    def test_draft_created_on_add_and_rebuilt_on_update(self):
        """评审 P1-1：add 同步建草稿 v1；内容变化递增 version；相同内容不递增。"""
        draft = self.session.exec(
            select(AgentProfileDraft).where(AgentProfileDraft.profile_id == self.profile.id)
        ).one()
        self.assertEqual(draft.draft_version, 1)
        self.assertIn("current_time", draft.draft_json)

        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="改名", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        draft2 = self.session.exec(
            select(AgentProfileDraft).where(AgentProfileDraft.profile_id == self.profile.id)
        ).one()
        self.assertEqual(draft2.draft_version, 2)
        self.assertIn("改名", draft2.draft_json)

        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="改名", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        draft3 = self.session.exec(
            select(AgentProfileDraft).where(AgentProfileDraft.profile_id == self.profile.id)
        ).one()
        self.assertEqual(draft3.draft_version, 2)  # hash 相同不递增

    def test_publish_full_flow_and_payload_boundary(self):
        """发布四步：快照完整 / is_current 唯一 / 载荷仅含绑定工具（P0-6 最小边界）。"""
        # 绑定之外的工具在资源层也存在（sync 同步了全部），但不得进入快照
        snapshot = self.service.publish(self.profile.id, current_user=self.owner)
        self.assertEqual(snapshot.version, 1)
        # 状态迁移：发布后 profile.status 必须为 published（走查实测缺陷——此前漏迁，
        # 前端 publishedProfiles 过滤恒空；单测盲区补断言）。self.profile 已被 add
        # 出口 expunge（tools 还原数组），按 id 重查取最新行
        self.assertEqual(self.session.get(AgentProfile, self.profile.id).status, AGENT_STATUS_PUBLISHED)
        self.assertIn("current_time", snapshot.snapshot_json)
        self.assertNotIn("query_asset", snapshot.snapshot_json)  # 未绑定不入快照
        import json

        payload = json.loads(snapshot.snapshot_json)
        self.assertEqual([t["toolName"] for t in payload["toolResourceSnapshots"]], ["current_time"])
        self.assertEqual(payload["guardrailsVersion"], "1")
        self.assertIn("systemPrompt", payload["profile"])

        record = self._current(self.profile.id)
        self.assertIsNotNone(record)
        self.assertEqual(record.snapshot_id, snapshot.id)
        self.assertEqual(record.action, "publish")

    def test_publish_idempotent_when_content_unchanged(self):
        """内容未变再次发布：幂等返回当前快照，不新建版本（评审 v1.4 P1）。"""
        first = self.service.publish(self.profile.id, current_user=self.owner)
        again = self.service.publish(self.profile.id, current_user=self.owner)
        self.assertEqual(first.id, again.id)
        versions = [s.version for s in self.service.list_snapshots(self.profile.id)]
        self.assertEqual(versions, [1])

    def test_publish_version_advances_after_change(self):
        """内容变化后再次发布：版本连续递增，is_current 切到新快照。"""
        self.service.publish(self.profile.id, current_user=self.owner)
        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="第二版", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        second = self.service.publish(self.profile.id, current_user=self.owner)
        self.assertEqual(second.version, 2)
        record = self._current(self.profile.id)
        self.assertEqual(record.snapshot_id, second.id)
        current = self.service.get_current_snapshot(self.profile.id)
        self.assertEqual(current["profile"]["name"], "第二版")

    def _page_rows(self, *ids: int) -> list[dict]:
        """走列表出口（_finalize_data，含 camelCase 转换）取行 dict。"""
        rows = []
        for pid in ids:
            entity = self.session.get(AgentProfile, pid)
            rows.append(self.service._row_to_dict(entity))
        return self.service._finalize_data(rows)

    def test_has_pending_changes_marks_draft_edits(self):
        """脏标记（发布与版本分析 P1-1）：draft 行恒 False；发布行草稿变更 → True；再发布 → False。"""
        # draft 态：无「已发布」基线，恒 False
        self.assertFalse(self._page_rows(self.profile.id)[0]["hasPendingChanges"])
        self.service.publish(self.profile.id, current_user=self.owner)
        self.assertFalse(self._page_rows(self.profile.id)[0]["hasPendingChanges"])
        # 草稿变更（未发布）→ True
        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="第二版", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        self.assertTrue(self._page_rows(self.profile.id)[0]["hasPendingChanges"])
        # 再发布 → 回到干净态
        self.service.publish(self.profile.id, current_user=self.owner)
        self.assertFalse(self._page_rows(self.profile.id)[0]["hasPendingChanges"])

    def test_current_snapshot_id_follows_publish_and_rollback(self):
        """current_snapshot_id（versions 端点 isCurrent 数据源）：随发布前进、随回滚切换。"""
        v1 = self.service.publish(self.profile.id, current_user=self.owner)
        self.assertEqual(self.service.current_snapshot_id(self.profile.id), v1.id)
        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="第二版", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        v2 = self.service.publish(self.profile.id, current_user=self.owner)
        self.assertEqual(self.service.current_snapshot_id(self.profile.id), v2.id)
        self.service.rollback(self.profile.id, v1.id, current_user=self.owner)
        self.assertEqual(self.service.current_snapshot_id(self.profile.id), v1.id)

    def test_publish_rejects_empty_tools(self):
        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="n", model_profile_code="deepseek-chat", tools=[]),
            current_user=self.owner,
        )
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(self.profile.id, current_user=self.owner)
        self.assertIn("至少绑定一个工具", ctx.exception.detail)

    def test_publish_rejects_window_overflow(self):
        """窗口严格模式（P1-2）：输入 6000 + 输出 30000 > 32000 → 拒绝发布。"""
        self.service.update(
            AgentProfileUpdateRequest(
                id=self.profile.id,
                name="n",
                model_profile_code="deepseek-chat",
                max_tokens=30000,
            ),
            current_user=self.owner,
        )
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(self.profile.id, current_user=self.owner)
        self.assertIn("窗口", ctx.exception.detail)

    def test_publish_rejects_disabled_tool(self):
        """资源层禁用工具不能发布（发布校验链：允许列表+已注册+启用）。"""
        row = self.session.exec(select(AgentToolResource).where(AgentToolResource.tool_name == "current_time")).one()
        row.status = False
        self.session.add(row)
        self.session.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(self.profile.id, current_user=self.owner)
        self.assertIn("禁用", ctx.exception.detail)

    def test_publish_and_rollback_require_creator_or_admin(self):
        """对象级操作权：非创建者发布/回滚 403（验收 21）。"""
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(self.profile.id, current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)
        first = self.service.publish(self.profile.id, current_user=self.owner)
        with self.assertRaises(HTTPException) as ctx:
            self.service.rollback(self.profile.id, first.id, current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rollback_switches_current_pointer(self):
        """回滚：不新建快照，is_current 切到目标快照并记录 rollback_from（验收 15）。"""
        first = self.service.publish(self.profile.id, current_user=self.owner)
        self.service.update(
            AgentProfileUpdateRequest(id=self.profile.id, name="第二版", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )
        second = self.service.publish(self.profile.id, current_user=self.owner)
        target = self.service.rollback(self.profile.id, first.id, current_user=self.owner)
        self.assertEqual(target.id, first.id)  # 不新建快照
        record = self._current(self.profile.id)
        self.assertEqual(record.snapshot_id, first.id)
        self.assertEqual(record.action, AGENT_PUBLISH_ACTION_ROLLBACK)
        self.assertEqual(record.rollback_from_snapshot_id, second.id)
        current = self.service.get_current_snapshot(self.profile.id)
        self.assertEqual(current["profile"]["name"], "测试智能体")  # 旧版内容回到运行面

    def test_toggle_enabled_realtime_not_frozen(self):
        """独立启停：实时生效、不经快照、不被发布冻结（评审 v1.4）。"""
        self.service.publish(self.profile.id, current_user=self.owner)
        self.service.toggle_enabled(self.profile.id, False, current_user=self.owner)
        entity = self.session.get(AgentProfile, self.profile.id)
        self.assertFalse(entity.enabled)
        current = self.service.get_current_snapshot(self.profile.id)
        self.assertIsNotNone(current)  # 快照不受影响
        with self.assertRaises(HTTPException) as ctx:
            self.service.toggle_enabled(self.profile.id, True, current_user=self.other)  # 非创建者 403
        self.assertEqual(ctx.exception.status_code, 403)
        entity = self.session.get(AgentProfile, self.profile.id)
        self.assertFalse(entity.enabled)  # 未被变更

    def test_name_uniqueness(self):
        """走查反馈：名称活跃行内唯一——add 撞名 400 / 改名撞他人 400 / 不改名直存排除自身 / 软删后可重建。"""
        with self.assertRaises(HTTPException) as ctx:
            self._create(name="测试智能体")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("名称", str(ctx.exception.detail))

        second = self._create(name="另一个智能体")
        with self.assertRaises(HTTPException) as ctx:
            self.service.update(
                AgentProfileUpdateRequest(id=second.id, name="测试智能体", model_profile_code="deepseek-chat"),
                current_user=self.owner,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        # 不改名直存：exclude_id 排除自身，不误伤
        self.service.update(
            AgentProfileUpdateRequest(id=second.id, name="另一个智能体", model_profile_code="deepseek-chat"),
            current_user=self.owner,
        )

        # 软删后同名可重建（partial unique 语义，与 code 一致）
        self.service.delete([second.id], current_user=self.owner)
        revived = self._create(name="另一个智能体")
        self.assertEqual(revived.name, "另一个智能体")


class ContextWindowPolicyTestCase(unittest.TestCase):
    """E15 渠道窗口动态化（A27）：齐备取最小 / 缺失拒绝 / 覆盖值生效 / 回退超预算拒绝。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                *_AI_CHANNEL_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.service = AgentProfileService(self.session)
        bootstrap_registry()
        sync_resources(self.session)
        self.owner = _FakeUser(1)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _create_profile(self, max_tokens: int = 4000) -> AgentProfile:
        return self.service.add(
            AgentProfileCreateRequest(
                name="窗口策略",
                model_profile_code="deepseek-chat",
                tools=["current_time"],
                max_tokens=max_tokens,
            ),
            current_user=self.owner,
        )

    def _model_row(self) -> AiModel:
        return self.session.exec(select(AiModel)).first()

    def test_chain_min_window_used(self):
        """齐备取最小：主 64000 + fallback 28000 → 链最小 28000，预算超它即拒绝。"""
        seed_chat_channel(
            self.engine,
            context_window=64000,
            fallback_code="deepseek-lite",
            fallback_context_window=28000,
        )
        profile = self._create_profile(max_tokens=26000)  # 6000+26000=32000 > 28000
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("28000", ctx.exception.detail)

    def test_unknown_window_rejects_publish(self):
        """缺失拒绝：任一候选 context_window=None → 未知不放行（不假设 ≥32k）。"""
        seed_chat_channel(self.engine, context_window=None)
        profile = self._create_profile()
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("未知窗口", ctx.exception.detail)

    def test_unknown_fallback_rejects_even_if_main_known(self):
        """主模型已知 + 回退未知 → 整链不可信，拒绝发布（E15 规则 2）。"""
        seed_chat_channel(
            self.engine,
            context_window=64000,
            fallback_code="deepseek-lite",
            fallback_context_window=None,
        )
        profile = self._create_profile()
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("未知窗口", ctx.exception.detail)

    def test_admin_override_value_takes_effect(self):
        """覆盖值生效：录入经验证窗口后同一绑定可发布（先拒后过）。"""
        seed_chat_channel(self.engine, context_window=None)
        profile = self._create_profile()
        with self.assertRaises(HTTPException):
            self.service.publish(profile.id, current_user=self.owner)
        row = self._model_row()
        row.context_window = 32000  # 管理员录入经验证覆盖值
        self.session.add(row)
        self.session.commit()
        snapshot = self.service.publish(profile.id, current_user=self.owner)
        self.assertIsNotNone(snapshot.id)

    def test_fallback_below_budget_rejects(self):
        """回退超预算拒绝：链最小窗口 < 预算 → 拒绝（A27 场景 4 的发起侧等价）。"""
        seed_chat_channel(
            self.engine,
            context_window=32000,
            fallback_code="deepseek-lite",
            fallback_context_window=9000,
        )
        profile = self._create_profile(max_tokens=8000)  # 6000+8000=14000 > 9000
        with self.assertRaises(HTTPException) as ctx:
            self.service.publish(profile.id, current_user=self.owner)
        self.assertIn("9000", ctx.exception.detail)


class ConcurrentPublishTestCase(unittest.TestCase):
    """并发发布不变量（验收 22）：is_current 至多一条、版本线无重复。

    R3（设计风险表）：FOR UPDATE 行锁与并发竞态的真验证在 CI/PG（TEST_DATABASE_URL 在位时
    运行）；本地内存 SQLite 的 StaticPool 单连接不支持双线程并发写（testing.mdc 基建约束），
    串行等价行为由 PublishProfileTestCase 的版本递增/幂等用例覆盖。
    """

    @classmethod
    def setUpClass(cls):
        import os

        if not os.environ.get("TEST_DATABASE_URL"):
            raise unittest.SkipTest("并发发布竞态需 PG（TEST_DATABASE_URL），本地 SQLite 单连接不支持并发写（R3）")

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                *_AI_CHANNEL_TABLES,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        bootstrap_registry()
        seed_chat_channel(self.engine)
        # 预置数据（主线程 session）
        session = Session(self.engine)
        sync_resources(session)
        service = AgentProfileService(session)
        self.profile = service.add(
            AgentProfileCreateRequest(name="并发", model_profile_code="deepseek-chat", tools=["current_time"]),
            current_user=_FakeUser(1),
        )
        session.close()

    def tearDown(self):
        self.engine.dispose()
        bootstrap_registry()

    def test_parallel_publishes_keep_invariants(self):
        """双线程同时发布：库级不变量保持（SQLite 下 FOR UPDATE 退化整库锁自然串行）。"""
        import threading

        results: list = []
        errors: list = []

        def worker(name: str):
            session = Session(self.engine)
            try:
                service = AgentProfileService(session)
                # 各自改名后发布（内容不同 → 各产生一个快照版本）
                service.update(
                    AgentProfileUpdateRequest(id=self.profile.id, name=name, model_profile_code="deepseek-chat"),
                    current_user=_FakeUser(1),
                )
                snapshot = service.publish(self.profile.id, current_user=_FakeUser(1))
                results.append((name, snapshot.version))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                session.close()

        t1 = threading.Thread(target=worker, args=("并发A",))
        t2 = threading.Thread(target=worker, args=("并发B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])
        session = Session(self.engine)
        try:
            records = session.exec(
                select(AgentProfilePublishRecord).where(
                    AgentProfilePublishRecord.profile_id == self.profile.id,
                    AgentProfilePublishRecord.is_current == True,  # noqa: E712
                )
            ).all()
            self.assertEqual(len(records), 1)  # is_current 至多一条（partial unique 兜底）
            versions = [
                s.version
                for s in session.exec(
                    select(AgentProfileSnapshot).where(AgentProfileSnapshot.profile_id == self.profile.id)
                ).all()
            ]
            self.assertEqual(len(versions), len(set(versions)))  # 版本线无重复
            self.assertEqual(len(results), 2)  # 两个发布都成功（串行化后）
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
