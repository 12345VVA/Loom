"""Phase 6 数据一致性修复验证测试。

覆盖：
- P1-6: transaction() 在 AUTOBEGIN + pending 场景正确提交，不再静默丢失写入。
- P1-11: 菜单 parent_id 环路检查，防止形成环、指向自身或引用不存在的父菜单。
"""

import os
import sys
import unittest
import warnings

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import transaction  # noqa: E402
from app.modules.base.model.auth import Menu  # noqa: E402
from app.modules.base.service.admin_service import MenuAdminService  # noqa: E402


class TxRow(SQLModel, table=True):
    """事务测试夹具表，仅在隔离 engine 上使用。"""

    __tablename__ = "test_phase6_tx_row"

    id: int | None = Field(default=None, primary_key=True)
    name: str


# 从全局 metadata 摘除夹具表，避免被 init_db() 的 create_all 带建到生产库。
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    SQLModel.metadata.remove(TxRow.__table__)


def _make_engine(tables):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=tables)
    return engine


class TransactionAutobeginPendingTests(unittest.TestCase):
    """P1-6: transaction() 在 AUTOBEGIN + pending 场景应提交而非静默丢失。"""

    def test_pending_autobegin_work_is_committed(self):
        engine = _make_engine([TxRow.__table__])

        with Session(engine) as session:
            # 先触发 AUTOBEGIN 并产生 pending 写入（不通过 transaction 上下文）。
            # 旧逻辑：transaction() 检测到 pending 误判为外层工作，不提交 → 写入静默丢失。
            # 新逻辑：检测到 origin=AUTOBEGIN，由本上下文提交 → 写入保留。
            session.add(TxRow(name="pending"))
            with transaction(session):
                session.add(TxRow(name="inner"))

            names = sorted(row.name for row in session.exec(select(TxRow)).all())
            self.assertEqual(names, ["inner", "pending"])

    def test_transaction_persists_across_new_session(self):
        """提交后用新 session 验证落库，避免 identity map 误判。"""
        engine = _make_engine([TxRow.__table__])

        with Session(engine) as session:
            session.add(TxRow(name="pending"))
            with transaction(session):
                session.add(TxRow(name="inner"))

        with Session(engine) as verify_session:
            names = sorted(row.name for row in verify_session.exec(select(TxRow)).all())
            self.assertEqual(names, ["inner", "pending"])

    def test_transaction_still_respects_explicit_begin(self):
        """显式 BEGIN 仍复用外层事务，不自行提交。"""
        engine = _make_engine([TxRow.__table__])

        with Session(engine) as session:
            with self.assertRaises(RuntimeError):
                with session.begin():
                    session.add(TxRow(name="outer"))
                    with transaction(session):
                        session.add(TxRow(name="inner"))
                    raise RuntimeError("rollback outer")
            self.assertEqual(session.exec(select(TxRow)).all(), [])

    def test_transaction_rolls_back_pending_on_autobegin(self):
        """AUTOBEGIN + pending 场景下抛异常，pending 写入应被回滚。"""
        engine = _make_engine([TxRow.__table__])

        with Session(engine) as session:
            session.add(TxRow(name="pending"))
            with self.assertRaises(RuntimeError):
                with transaction(session):
                    session.add(TxRow(name="inner"))
                    raise RuntimeError("boom")
            # 回滚后两行均不应存在
            self.assertEqual(session.exec(select(TxRow)).all(), [])


class MenuParentCycleTests(unittest.TestCase):
    """P1-11: 菜单 parent_id 环路检查。"""

    def _make_service(self):
        engine = _make_engine([Menu.__table__])
        session = Session(engine)
        return engine, session, MenuAdminService(session)

    @staticmethod
    def _create_menu(session, code, name=None, parent_id=None):
        menu = Menu(code=code, name=name or code, parent_id=parent_id, type="menu")
        session.add(menu)
        session.commit()
        session.refresh(menu)
        return menu

    def test_update_parent_to_self_rejected(self):
        """parent_id 指向自身应被拒绝。"""
        _, session, svc = self._make_service()
        try:
            menu = self._create_menu(session, "m_self")
            with self.assertRaises(HTTPException) as ctx:
                svc._validate_parent_id(menu.id, menu_id=menu.id)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("自身", ctx.exception.detail)
        finally:
            session.close()

    def test_update_parent_forming_cycle_rejected(self):
        """父级设置导致祖先链回到自身应被拒绝。"""
        _, session, svc = self._make_service()
        try:
            # 构建链: A <- B <- C（C 的父是 B，B 的父是 A）
            a = self._create_menu(session, "m_a")
            b = self._create_menu(session, "m_b", parent_id=a.id)
            c = self._create_menu(session, "m_c", parent_id=b.id)
            # 把 A 的父设为 C，将形成环 A -> C -> B -> A
            with self.assertRaises(HTTPException) as ctx:
                svc._validate_parent_id(c.id, menu_id=a.id)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("环路", ctx.exception.detail)
        finally:
            session.close()

    def test_update_parent_to_nonexistent_rejected(self):
        """父菜单不存在应被拒绝。"""
        _, session, svc = self._make_service()
        try:
            menu = self._create_menu(session, "m_exist")
            with self.assertRaises(HTTPException) as ctx:
                svc._validate_parent_id(999999, menu_id=menu.id)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("不存在", ctx.exception.detail)
        finally:
            session.close()

    def test_update_parent_to_root_allowed(self):
        """parent_id 设为 None（根菜单）应放行。"""
        _, session, svc = self._make_service()
        try:
            a = self._create_menu(session, "m_root_a")
            b = self._create_menu(session, "m_root_b", parent_id=a.id)
            # 将 B 的父设为 None（根菜单），应放行
            svc._validate_parent_id(None, menu_id=b.id)
        finally:
            session.close()

    def test_update_parent_to_ancestor_allowed(self):
        """更新为合法祖先（非子孙）应放行，不误报环路。"""
        _, session, svc = self._make_service()
        try:
            a = self._create_menu(session, "m_ok_a")
            b = self._create_menu(session, "m_ok_b", parent_id=a.id)
            c = self._create_menu(session, "m_ok_c", parent_id=b.id)
            # 把 C 的父从 B 改为 A（A 是 C 的祖先但非子孙），合法
            svc._validate_parent_id(a.id, menu_id=c.id)
        finally:
            session.close()

    def test_add_with_nonexistent_parent_rejected(self):
        """add 时父菜单不存在应被拒绝。"""
        _, session, svc = self._make_service()
        try:
            with self.assertRaises(HTTPException) as ctx:
                svc._validate_parent_id(999999)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("不存在", ctx.exception.detail)
        finally:
            session.close()

    def test_add_with_existing_parent_allowed(self):
        """add 时父菜单存在应放行。"""
        _, session, svc = self._make_service()
        try:
            parent = self._create_menu(session, "m_parent")
            svc._validate_parent_id(parent.id)
        finally:
            session.close()

    def test_before_update_rejects_cycle_via_service(self):
        """通过 _before_update 端到端验证环路被拒。"""
        _, session, svc = self._make_service()
        try:
            a = self._create_menu(session, "m_chain_a")
            b = self._create_menu(session, "m_chain_b", parent_id=a.id)
            # 把 A 的 parent_id 改为 B（B 是 A 的子），应被 _before_update 拒绝
            with self.assertRaises(HTTPException) as ctx:
                svc._before_update({"parent_id": b.id}, entity=a)
            self.assertEqual(ctx.exception.status_code, 400)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
