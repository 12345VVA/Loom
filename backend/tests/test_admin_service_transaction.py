"""
admin_service.py 事务一致性验证测试。

覆盖：
1. BaseAdminCrudService.add: 实体与 _after_add 纳入统一事务，发生异常整体回滚。
2. BaseAdminCrudService.update: 实体更新、_log_entity_change 与 _after_update 纳入统一事务，保证原子性。
3. BaseAdminCrudService.delete: 实体删除、_log_entity_change 与 _after_delete 纳入统一事务，且修复 _after_delete 被调用的问题。
4. UserAdminService / RoleAdminService: 级联操作（如角色与菜单绑定）异常时，主实体事务被正确回滚，防止脏数据。
"""

import os
import sys
import unittest
from typing import Any

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.base.model.auth import Menu, Role, RoleMenuLink, User, UserRoleLink  # noqa: E402
from app.modules.base.model.sys import SysLog, SysSecurityLog  # noqa: E402
from app.modules.base.service.admin_service import (  # noqa: E402
    BaseAdminCrudService,
    RoleAdminService,
    UserAdminService,
)


from datetime import datetime

class DummyEntity(SQLModel, table=True):
    __tablename__ = "test_dummy_crud_entity"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    age: int = 0
    delete_time: datetime | None = None


def _make_isolated_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[
            DummyEntity.__table__,
            SysLog.__table__,
            SysSecurityLog.__table__,
            User.__table__,
            Role.__table__,
            Menu.__table__,
            UserRoleLink.__table__,
            RoleMenuLink.__table__,
        ],
    )
    return engine


class AdminServiceTransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = _make_isolated_engine()

    def test_add_rollback_when_after_add_fails(self):
        """测试在 _after_add 钩子抛出异常时，主实体自动回滚，无残留脏数据。"""

        class FailingService(BaseAdminCrudService):
            def _after_add(self, entity: Any, payload: Any = None) -> None:
                raise RuntimeError("hook error")

        with Session(self.engine) as session:
            svc = FailingService(session, DummyEntity)
            with self.assertRaises(RuntimeError):
                svc.add({"name": "alice", "age": 20})

        with Session(self.engine) as verify_session:
            rows = verify_session.exec(select(DummyEntity)).all()
            self.assertEqual(len(rows), 0, "事务回滚失败，产生了残留实体")

    def test_update_persists_log_and_rolls_back_atomically(self):
        """测试 update 时 _log_entity_change 在同一事务中提交，且在钩子异常时一同回滚。"""
        with Session(self.engine) as session:
            svc = BaseAdminCrudService(session, DummyEntity)
            entity = svc.add({"name": "bob", "age": 25})
            entity_id = entity.id

        # 1. 正常 update：验证实体变更与 SysLog 同步落库
        with Session(self.engine) as session:
            svc = BaseAdminCrudService(session, DummyEntity)
            svc.update({"id": entity_id, "name": "bob_updated"})

        with Session(self.engine) as verify_session:
            row = verify_session.get(DummyEntity, entity_id)
            self.assertEqual(row.name, "bob_updated")
            logs = verify_session.exec(select(SysLog).where(SysLog.action == "/admin/dummyentity/update")).all()
            self.assertEqual(len(logs), 1, "SysLog 应该在 update 事务中成功提交落库")

        # 2. _after_update 异常：验证实体与日志原子回滚
        class FailingUpdateService(BaseAdminCrudService):
            def _after_update(self, entity: Any, payload: Any = None) -> None:
                raise RuntimeError("update hook failed")

        with Session(self.engine) as session:
            svc = FailingUpdateService(session, DummyEntity)
            with self.assertRaises(RuntimeError):
                svc.update({"id": entity_id, "name": "bob_should_fail"})

        with Session(self.engine) as verify_session:
            row = verify_session.get(DummyEntity, entity_id)
            self.assertEqual(row.name, "bob_updated", "实体更新应该被回滚")
            # 日志条数保持为 1，本次 update 的日志不能提交
            logs = verify_session.exec(select(SysLog).where(SysLog.action == "/admin/dummyentity/update")).all()
            self.assertEqual(len(logs), 1, "回滚时新增的操作日志不应该落库")

    def test_delete_invokes_after_delete_and_logs(self):
        """测试 delete 时 _after_delete 被正确触发，且删除日志一同落库。"""
        hook_called = []

        class TrackingDeleteService(BaseAdminCrudService):
            def _after_delete(self, ids: list[int], payload: Any = None) -> None:
                hook_called.extend(ids)

        with Session(self.engine) as session:
            svc = TrackingDeleteService(session, DummyEntity)
            e1 = svc.add({"name": "del1", "age": 10})
            e2 = svc.add({"name": "del2", "age": 20})
            id1, id2 = e1.id, e2.id

            result = svc.delete([id1, id2])
            self.assertTrue(result["success"])

        # 验证 _after_delete 钩子确被调用
        self.assertCountEqual(hook_called, [id1, id2], "_after_delete 钩子未被触发或参数错误")

        # 验证 SysLog 已落库
        with Session(self.engine) as verify_session:
            remaining = verify_session.exec(select(DummyEntity)).all()
            self.assertEqual(len(remaining), 0)
            logs = verify_session.exec(select(SysLog).where(SysLog.action == "/admin/dummyentity/delete")).all()
            self.assertEqual(len(logs), 2, "删除日志应该落库")

    def test_role_admin_service_rollback_on_invalid_menu_ids(self):
        """测试 RoleAdminService 在传入非法 menu_ids 时，整个角色创建被完整回滚。"""
        with Session(self.engine) as session:
            role_svc = RoleAdminService(session)
            payload = {
                "name": "test_role",
                "code": "test_role_code",
                "label": "test_role",
                "menu_ids": [999999],  # 不存在的菜单
            }

            with self.assertRaises(HTTPException) as cm:
                role_svc.add(payload)
            self.assertEqual(cm.exception.status_code, 404)

        with Session(self.engine) as verify_session:
            roles = verify_session.exec(select(Role).where(Role.code == "test_role_code")).all()
            self.assertEqual(len(roles), 0, "创建角色时关联失败，角色实体必须被完整回滚！")

    def test_user_admin_service_rollback_on_invalid_role_ids(self):
        """测试 UserAdminService 在传入非法 role_ids 时，整个用户创建被完整回滚。"""
        with Session(self.engine) as session:
            user_svc = UserAdminService(session)
            payload = {
                "username": "atomic_user",
                "password": "Password123!",
                "full_name": "Atomic User",
                "role_ids": [888888],  # 不存在的角色
            }

            with self.assertRaises(HTTPException) as cm:
                user_svc.add(payload)
            self.assertEqual(cm.exception.status_code, 404)

        with Session(self.engine) as verify_session:
            users = verify_session.exec(select(User).where(User.username == "atomic_user")).all()
            self.assertEqual(len(users), 0, "创建用户时角色关联失败，用户实体必须被完整回滚！")
