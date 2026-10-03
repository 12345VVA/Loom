"""bootstrap_defaults 批量 upsert 的幂等性回归。

覆盖四条对账语义：首建全量、稳态重跑计数不变、
孤儿清扫（受管前缀删 / 用户自建留）、parent 挂载修正与顶级回滚。
"""

import os
import sys
import unittest

from sqlmodel import Session, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from helpers import make_test_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.base.model.auth import (  # noqa: E402
    Department,
    Menu,
    Role,
    RoleDepartmentLink,
    RoleMenuLink,
    User,
    UserRoleLink,
)
from app.modules.base.service.auth_service import AuthService  # noqa: E402
from app.modules.loader import load_menu_manifest_items  # noqa: E402

BOOTSTRAP_TABLES = [
    Department.__table__,
    Menu.__table__,
    Role.__table__,
    RoleDepartmentLink.__table__,
    RoleMenuLink.__table__,
    User.__table__,
    UserRoleLink.__table__,
]


def _counts(session: Session) -> dict[str, int]:
    return {
        "menu": len(session.exec(select(Menu)).all()),
        "role": len(session.exec(select(Role)).all()),
        "user": len(session.exec(select(User)).all()),
        "role_menu": len(session.exec(select(RoleMenuLink)).all()),
    }


class BootstrapDefaultsIdempotentTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine(tables=BOOTSTRAP_TABLES)

    def _run(self) -> None:
        with Session(self.engine) as session:
            AuthService(session).bootstrap_defaults()

    def test_first_run_creates_full_bootstrap(self):
        manifest = load_menu_manifest_items()
        self._run()
        with Session(self.engine) as session:
            self.assertEqual({m.code for m in session.exec(select(Menu)).all()}, {i.code for i in manifest})
            self.assertEqual({r.code for r in session.exec(select(Role)).all()}, {"admin", "task_operator"})
            self.assertIsNotNone(
                session.exec(select(Department).where(Department.name == "平台")).first(),
                "应创建平台根部门",
            )
            admin = session.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
            self.assertIsNotNone(admin, "应创建默认管理员")
            admin_role = session.exec(select(Role).where(Role.code == "admin")).first()
            self.assertTrue(
                session.exec(
                    select(UserRoleLink).where(UserRoleLink.user_id == admin.id, UserRoleLink.role_id == admin_role.id)
                ).first(),
                "管理员应绑定 admin 角色",
            )

    def test_second_run_keeps_counts(self):
        self._run()
        with Session(self.engine) as session:
            first = _counts(session)
        self._run()
        with Session(self.engine) as session:
            self.assertEqual(_counts(session), first, "稳态重跑不应产生任何新行")

    def test_orphan_cleanup_and_custom_menu_preserved(self):
        self._run()
        with Session(self.engine) as session:
            session.add(Menu(name="孤儿", code="sys_fake_orphan", type="menu"))
            session.add(Menu(name="自建", code="my_custom_menu", type="menu"))
            session.commit()
        self._run()
        with Session(self.engine) as session:
            codes = {m.code for m in session.exec(select(Menu)).all()}
            self.assertNotIn("sys_fake_orphan", codes, "受管前缀且不在 manifest 的菜单应被清扫")
            self.assertIn("my_custom_menu", codes, "非受管的自建菜单不应被误删")
            self.assertEqual(len(codes), len({i.code for i in load_menu_manifest_items()}) + 1, "仅自建菜单额外保留")

    def test_parent_reassignment_and_top_level_reset(self):
        self._run()
        manifest = load_menu_manifest_items()
        child_item = next(i for i in manifest if i.parent_code)
        top_item = next(i for i in manifest if not i.parent_code)
        with Session(self.engine) as session:
            menus = {m.code: m for m in session.exec(select(Menu)).all()}
            correct_parent_id = menus[child_item.parent_code].id
            # 子菜单挂错父 + 顶级菜单被错挂分组
            menus[child_item.code].parent_id = menus[top_item.code].id
            menus[top_item.code].parent_id = menus[child_item.parent_code].id
            session.add_all([menus[child_item.code], menus[top_item.code]])
            session.commit()
        self._run()
        with Session(self.engine) as session:
            menus = {m.code: m for m in session.exec(select(Menu)).all()}
            self.assertEqual(
                menus[child_item.code].parent_id, correct_parent_id, "错挂的子菜单应回正到 manifest 指定父"
            )
            self.assertIsNone(menus[top_item.code].parent_id, "顶级菜单的历史挂载应被回滚为 None")


if __name__ == "__main__":
    unittest.main()
