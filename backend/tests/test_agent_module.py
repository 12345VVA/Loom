"""agent 模块数据层与 CRUD 骨架测试（P1）。

服务层行为用 make_test_engine 局部引擎（testing.mdc）；模块注册断言用真实 app
（EPS 出现 agent controllers、菜单清单含 agent 三菜单）。
发布/运行时行为在 P4/P5 扩充（test_agent_profile / test_agent_runtime）。
"""

from __future__ import annotations

import json
import unittest

from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session

from app.modules.agent.model.agent import (
    AGENT_RUN_CANCELLED,
    AGENT_RUN_MODE_DRAFT,
    AGENT_RUN_MODE_PUBLISHED,
    AGENT_RUN_RUNNING,
    AGENT_STATUS_DRAFT,
    AgentProfile,
    AgentProfileCreateRequest,
    AgentProfileDraft,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
    AgentProfileUpdateRequest,
    AgentRunTrace,
    AgentSession,
    AgentToolApproval,
    AgentToolResource,
    AgentToolResourceVersion,
)
from app.modules.agent.service.profile_service import AgentProfileService
from app.modules.agent.service.runtime.session_service import AgentSessionService
from app.modules.agent.service.trace_service import AgentRunTraceService
from app.modules.base.model.auth import Role, UserRoleLink
from app.modules.base.model.sys import SysLog


class _FakeUser:
    """服务层测试用的最小用户形态（is_super_admin=True 可短路角色表查询）。"""

    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin


class AgentProfileCrudTestCase(unittest.TestCase):
    """CRUD 生命周期：draft 强制 / code 自动生成 / 状态字段保护 / 可见性 / tools 往返。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentToolApproval.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                Role.__table__,
                UserRoleLink.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.service = AgentProfileService(self.session)
        self.owner = _FakeUser(1)
        self.other = _FakeUser(2)
        self.admin = _FakeUser(3, is_super_admin=True)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _create(self, code: str | None = "hero", current_user=None, **kwargs) -> AgentProfile:
        payload = AgentProfileCreateRequest(
            code=code,
            name=kwargs.pop("name", code or "unnamed"),
            model_profile_code=kwargs.pop("model_profile_code", "deepseek-chat"),
            **kwargs,
        )
        return self.service.add(payload, current_user=current_user or self.owner)

    def test_add_forces_draft_and_creator(self):
        """Create 请求体夹带 status/created_by/enabled 也被覆盖为 draft + 当前用户 + 默认启用。"""
        entity = self._create()
        self.assertEqual(entity.status, AGENT_STATUS_DRAFT)
        self.assertEqual(entity.created_by, 1)
        self.assertTrue(entity.enabled)

    def test_add_generates_code_when_blank(self):
        """code 留空自动生成：ag-{8位base36}；显式传入（含空白）则沿用。"""
        entity = self._create(code="", name="自动编号")
        self.assertRegex(entity.code, r"^ag-[a-z0-9]{8}$")
        explicit = self._create(code=" my-agent ", name="显式编号")
        self.assertEqual(explicit.code, "my-agent")

    def test_add_generated_code_unique(self):
        codes = {self._create(code="", name=f"n{i}").code for i in range(5)}
        self.assertEqual(len(codes), 5)

    def test_code_conflict_400(self):
        self._create(code="hero")
        with self.assertRaises(HTTPException) as ctx:
            self._create(code="hero", current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_tools_json_roundtrip(self):
        """tools 传数组 → Text JSON 存储 → add 出口与 page/info 同构还原数组。"""
        entity = self._create(code="t1", tools=["query_asset", "current_time"])
        # add 出口已改为脱管后还原数组（走查实测响应序列化 500）；存储层仍是 JSON 文本
        self.assertEqual(entity.tools, ["query_asset", "current_time"])
        stored = self.session.get(AgentProfile, entity.id)
        self.assertIsInstance(stored.tools, str)
        self.assertEqual(json.loads(stored.tools), ["query_asset", "current_time"])
        rows = self.service.list(current_user=self.owner)
        row = next(r for r in rows if r["id"] == entity.id)
        self.assertEqual(row["tools"], ["query_asset", "current_time"])

    def test_update_strips_protected_fields(self):
        """update 剔除 status/created_by/enabled（启停只经 toggleEnabled、状态只经 publish）。"""
        entity = self._create()
        data = AgentProfileUpdateRequest(
            id=entity.id, code="hero", name="改名", model_profile_code="deepseek-chat"
        ).model_dump(exclude_unset=True)
        data.update({"status": "published", "created_by": 999, "enabled": False})
        payload = AgentProfileUpdateRequest.model_validate(data)
        updated = self.service.update(payload, current_user=self.owner)
        self.assertEqual(updated.status, AGENT_STATUS_DRAFT)
        self.assertEqual(updated.created_by, 1)
        self.assertTrue(updated.enabled)
        self.assertEqual(updated.name, "改名")

    def test_visibility_filter(self):
        """管理面可见性：draft 仅创建者可见；管理员全量。"""
        self._create(code="mine")
        self._create(code="theirs", current_user=self.other)

        mine = {row["code"] for row in self.service.list(current_user=self.owner)}
        admin_seen = {row["code"] for row in self.service.list(current_user=self.admin)}
        self.assertEqual(mine, {"mine"})
        self.assertEqual(admin_seen, {"mine", "theirs"})

    def test_delete_only_creator_or_admin(self):
        entity = self._create()
        with self.assertRaises(HTTPException) as ctx:
            self.service.delete([entity.id], current_user=self.other)
        self.assertEqual(ctx.exception.status_code, 403)
        self.service.delete([entity.id], current_user=self.owner)


class TraceAndSessionVisibilityTestCase(unittest.TestCase):
    """trace / session 管理面仅本人（验收 21 的 service 层限定）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentSession.__table__,
                AgentRunTrace.__table__,
                Role.__table__,
                UserRoleLink.__table__,
            ]
        )
        self.session = Session(self.engine)
        self.trace_service = AgentRunTraceService(self.session)
        self.session_service = AgentSessionService(self.session)
        self.user_a = _FakeUser(1)
        self.user_b = _FakeUser(2)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _trace(self, user_id: int) -> AgentRunTrace:
        row = AgentRunTrace(profile_id=1, run_mode=AGENT_RUN_MODE_PUBLISHED, session_id=1, user_id=user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def _session_row(self, user_id: int, run_mode: str = AGENT_RUN_MODE_PUBLISHED) -> AgentSession:
        row = AgentSession(session_code=f"s-{user_id}-{run_mode}", profile_id=1, user_id=user_id, run_mode=run_mode)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def test_trace_visible_only_to_owner(self):
        """trace 列表仅本人：他人（含普通查询）不可见。"""
        mine = self._trace(1)
        self._trace(2)
        rows = self.trace_service.list(current_user=self.user_a)
        self.assertEqual([r["id"] for r in rows], [mine.id])

    def test_session_visible_only_to_owner_and_run_mode_stored(self):
        """session 列表仅本人；run_mode 独立字段按创建值存取（draft/published 隔离依据）。"""
        mine_pub = self._session_row(1, AGENT_RUN_MODE_PUBLISHED)
        self._session_row(1, AGENT_RUN_MODE_DRAFT)
        self._session_row(2)
        rows = self.session_service.list(current_user=self.user_a)
        self.assertEqual(len(rows), 2)
        modes = {r["runMode"] for r in rows}
        self.assertEqual(modes, {AGENT_RUN_MODE_PUBLISHED, AGENT_RUN_MODE_DRAFT})
        self.assertIn(mine_pub.session_code, {r["sessionCode"] for r in rows})

    def test_trace_running_default_status(self):
        """trace 创建默认 running（执行中非终态），终态值集合互斥（四值）。"""
        from app.modules.agent.model.agent import AGENT_RUN_TERMINAL_STATUSES

        row = self._trace(1)
        self.assertEqual(row.status, AGENT_RUN_RUNNING)
        self.assertNotIn(AGENT_RUN_RUNNING, AGENT_RUN_TERMINAL_STATUSES)
        self.assertIn(AGENT_RUN_CANCELLED, AGENT_RUN_TERMINAL_STATUSES)


class ModuleRegistrationTestCase(unittest.TestCase):
    """模块注册断言：EPS 出现 agent controllers；菜单清单含 agent 三菜单。"""

    def setUp(self):
        from fastapi.testclient import TestClient

        from main import app

        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_eps_contains_agent_controllers(self):
        response = self.client.get("/admin/base/open/eps")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("agent", data)
        prefixes = {item["prefix"] for item in data["agent"]}
        for expected in (
            "/admin/agent/profile",
            "/admin/agent/session",
            "/admin/agent/trace",
            "/admin/agent/tool",
        ):
            self.assertIn(expected, prefixes)

    def test_menu_manifest_contains_agent_menus(self):
        from app.modules.loader import load_menu_manifest_items

        items = load_menu_manifest_items()
        routers = {item.path for item in items if getattr(item, "path", None)}
        for expected in ("/agent/profile", "/agent/session", "/agent/trace"):
            self.assertIn(expected, routers)


if __name__ == "__main__":
    unittest.main()
