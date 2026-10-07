"""QA 独立验证：通知模块 7 项修复（F1-F7）——后端侧针对性用例。

本文件为独立验证产物（不修改任何业务源码），覆盖：
- F1 `_insert_recipients` 批量插入：SQL 次数下降 + 去重语义不变 + `_send` 端到端数量；
- F2 `unread_count` 计数口径与 `list_for_user` 对齐 + 返回 int；
- F3 `list_for_user` 归档过滤下推 SQL 与旧 Python 侧过滤等价 + 分页 + 控制器夹取；
- F4 `super_admins` 停用账号不再投递，且与 `active_admins` 语义统一。

运行：
    cd backend && ./venv/Scripts/python.exe -m pytest tests/test_notification_fixes.py -q
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlmodel import Session, SQLModel, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from helpers import make_test_engine  # noqa: E402

from app.modules.base.model.auth import Department, Role, User, UserRoleLink  # noqa: E402
from app.modules.notification.controller.admin.message import NotificationMessageController  # noqa: E402
from app.modules.notification.model.notification import (  # noqa: E402
    AudienceRule,
    NotificationMessage,
    NotificationRecipient,
    NotificationTemplate,
)
from app.modules.notification.service.notification_service import (  # noqa: E402
    NotificationMessageService,
    NotificationService,
)


class SQLRecorder:
    """基于 SQLAlchemy 事件的 SQL 语句计数器（按语句首词分类，记录是否 executemany）。"""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[tuple[str, bool]] = []

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on)
        return False

    def _on(self, conn, cursor, statement, parameters, context, executemany):
        verb = statement.strip().split()[0].upper() if statement.strip() else ""
        self.statements.append((verb, bool(executemany)))

    def count(self, verb: str) -> int:
        return sum(1 for v, _ in self.statements if v == verb)

    def summary(self) -> str:
        from collections import Counter

        return dict(Counter(v for v, _ in self.statements))


class NotificationFixesTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Role.__table__,
                Department.__table__,
                UserRoleLink.__table__,
                NotificationMessage.__table__,
                NotificationRecipient.__table__,
                NotificationTemplate.__table__,
            ],
        )

    # ---------- 夹具 ----------
    def _seed_users(self, session: Session, n: int = 5) -> list[User]:
        dept = Department(name="研发", parent_id=None)
        session.add(dept)
        session.commit()
        session.refresh(dept)
        users = [
            User(username=f"u{i}", full_name=f"u{i}", password_hash="x", is_active=True, department_id=dept.id)
            for i in range(n)
        ]
        session.add_all(users)
        session.commit()
        for u in users:
            session.refresh(u)
        return users

    def _new_message(self, session: Session, *, created_at: datetime | None = None, **kw) -> NotificationMessage:
        msg = NotificationMessage(title=kw.pop("title", "t"), content=kw.pop("content", "c"), **kw)
        if created_at is not None:
            msg.created_at = created_at
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return msg

    def _new_recipient(self, session: Session, message_id: int, user_id: int, **kw) -> NotificationRecipient:
        rec = NotificationRecipient(message_id=message_id, user_id=user_id, **kw)
        session.add(rec)
        session.commit()
        session.refresh(rec)
        return rec

    # ---------- B. F1：批量插入 ----------
    def test_f1_insert_recipients_sql_count_drops(self):
        """B1：N=5 收件人，改动后查重 SELECT 由 N 降到 1（IN 一次）。

        注意：为贴近真实 `_send` 流程，用户加载后**不再 commit**（commit 会 expire 所有
        对象，随后访问 user.id/department_id 会触发 lazy reload，人为放大 SELECT）。
        这里用 flush 取 message.id，使测得的是纯查重 SQL。
        """
        with Session(self.engine) as session:
            users = self._seed_users(session, n=5)
            svc = NotificationService(session)

            # 新建 message 但只 flush 取 id（不 commit），避免 user 对象 expire
            msg = NotificationMessage(title="t", content="c")
            session.add(msg)
            session.flush()

            with SQLRecorder(self.engine) as rec:
                rows = svc._insert_recipients(msg, users)
                dedup_select = rec.count("SELECT")
                session.flush()
                full = rec.summary()
            print(f"\n[F1] new _insert_recipients N=5 → dedup SELECT={dedup_select}, full SQL={full}")
            self.assertEqual(len(rows), 5)
            self.assertEqual(dedup_select, 1, "改动后查重应为单条 IN SELECT（N→1）")

            # 旧逻辑推演：逐用户 select(...).first() 查重（同 session、同不 expire 前提）
            msg2 = NotificationMessage(title="t2", content="c")
            session.add(msg2)
            session.flush()
            with SQLRecorder(self.engine) as rec2:
                for user in users:
                    session.exec(
                        select(NotificationRecipient).where(
                            NotificationRecipient.message_id == msg2.id,
                            NotificationRecipient.user_id == user.id,
                        )
                    ).first()
                legacy_select = rec2.count("SELECT")
            print(f"[F1] legacy per-user check N=5 → dedup SELECT={legacy_select}")
            self.assertEqual(legacy_select, 5, "旧逻辑每用户一次查重 SELECT = N（2N 中的 N 次查重）")

    def test_f1_insert_recipients_idempotent_within_txn(self):
        """B2：同一 message 未提交前重复调用，第二次不应重复插入（去重语义不变）。"""
        with Session(self.engine) as session:
            users = self._seed_users(session, n=5)
            msg = self._new_message(session)
            svc = NotificationService(session)

            first = svc._insert_recipients(msg, users)
            second = svc._insert_recipients(msg, users)
            self.assertEqual(len(first), 5)
            self.assertEqual(second, [], "第二次调用应返回空列表（全部已存在）")
            session.commit()
            total = session.exec(select(NotificationRecipient).where(NotificationRecipient.message_id == msg.id)).all()
            self.assertEqual(len(total), 5, "DB 中收件人总数不应翻倍")

    def test_f1_send_end_to_end_recipient_count(self):
        """B3：`_send` 端到端仍产生正确收件人数量。"""
        with Session(self.engine) as session:
            users = self._seed_users(session, n=5)
            ids = [u.id for u in users]
            result = NotificationService(session).send(
                title="全量", content="x", audience=AudienceRule(users=ids), message_type="business"
            )
            self.assertEqual(result.recipient_count, 5)
            db_rows = session.exec(
                select(NotificationRecipient).where(NotificationRecipient.message_id == result.message.id)
            ).all()
            self.assertEqual(len({r.user_id for r in db_rows}), 5)

    # ---------- C. F2：计数口径 ----------
    def test_f2_unread_count_matches_list_and_returns_int(self):
        """C1/C2：混合数据集下 unread_count 口径与 list_for_user(unread) 一致，且返回 int。"""
        with Session(self.engine) as session:
            u = self._seed_users(session, n=1)[0]

            # msg1: 未读、未归档、有效 -> 计入
            m1 = self._new_message(session, created_at=datetime(2026, 1, 1, tzinfo=UTC))
            self._new_recipient(session, m1.id, u.id, is_read=False, is_archived=False)
            # msg2: 已读 -> 不计
            m2 = self._new_message(session, created_at=datetime(2026, 1, 2, tzinfo=UTC))
            self._new_recipient(session, m2.id, u.id, is_read=True, is_archived=False)
            # msg3: 未读但已归档 -> 不计
            m3 = self._new_message(session, created_at=datetime(2026, 1, 3, tzinfo=UTC))
            self._new_recipient(session, m3.id, u.id, is_read=False, is_archived=True)
            # msg4: 未读但消息已召回 -> 不计
            m4 = self._new_message(session, created_at=datetime(2026, 1, 4, tzinfo=UTC), is_recalled=True)
            self._new_recipient(session, m4.id, u.id, is_read=False, is_archived=False)
            # msg5: 未读但消息已过期 -> 不计
            m5 = self._new_message(
                session, created_at=datetime(2026, 1, 5, tzinfo=UTC), expired_at=datetime.now(UTC) - timedelta(hours=1)
            )
            self._new_recipient(session, m5.id, u.id, is_read=False, is_archived=False)
            # msg6: 未读但消息软删除 -> 不计
            m6 = self._new_message(session, created_at=datetime(2026, 1, 6, tzinfo=UTC))
            self._new_recipient(session, m6.id, u.id, is_read=False, is_archived=False)
            m6.delete_time = datetime.now(UTC)
            session.add(m6)
            session.commit()
            # msg7: 未读但收件人被软删除 -> 不计
            m7 = self._new_message(session, created_at=datetime(2026, 1, 7, tzinfo=UTC))
            self._new_recipient(session, m7.id, u.id, is_read=False, is_archived=False, is_deleted=True)

            svc = NotificationMessageService(session)
            count = svc.unread_count(u.id)
            listed = svc.list_for_user(u.id, read_status="unread")
            print(f"\n[F2] unread_count={count} (type={type(count).__name__}), list(unread) len={len(listed)}")
            self.assertIsInstance(count, int)
            self.assertEqual(count, 1)
            self.assertEqual(count, len(listed), "unread_count 应与 list_for_user(read_status='unread') 长度一致")

    # ---------- D. F3：归档下推 + 分页 ----------
    def _legacy_list(self, session, user_id, include_archived, read_status):
        """旧实现等价参考：不加归档 SQL 条件，在 Python 侧用两处 continue 过滤。"""
        statement = (
            select(NotificationMessage, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.message_id == NotificationMessage.id)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_deleted == False,  # noqa: E712
                NotificationMessage.is_recalled == False,  # noqa: E712
                NotificationMessage.delete_time.is_(None),
            )
            .order_by(NotificationMessage.created_at.desc())
        )
        now = datetime.now(UTC)
        statement = statement.where((NotificationMessage.expired_at.is_(None)) | (NotificationMessage.expired_at > now))
        if read_status == "unread":
            statement = statement.where(NotificationRecipient.is_read == False)  # noqa: E712
        elif read_status == "read":
            statement = statement.where(NotificationRecipient.is_read == True)  # noqa: E712
        out = []
        for _message, recipient in session.exec(statement).all():
            if recipient.is_archived and not include_archived:
                continue
            if include_archived and read_status == "archived" and not recipient.is_archived:
                continue
            out.append(recipient.id)
        return set(out)

    def test_f3_archive_pushdown_equivalent_to_legacy(self):
        """D1：4 种组合下新（SQL 下推）与旧（Python 过滤）结果完全一致。"""
        with Session(self.engine) as session:
            users = self._seed_users(session, n=1)
            u = users[0]
            # A 未读未归档 / B 已读未归档 / C 未读已归档 / D 已读已归档
            a = self._new_message(session, created_at=datetime(2026, 2, 1, tzinfo=UTC))
            self._new_recipient(session, a.id, u.id, is_read=False, is_archived=False)
            b = self._new_message(session, created_at=datetime(2026, 2, 2, tzinfo=UTC))
            self._new_recipient(session, b.id, u.id, is_read=True, is_archived=False)
            c = self._new_message(session, created_at=datetime(2026, 2, 3, tzinfo=UTC))
            self._new_recipient(session, c.id, u.id, is_read=False, is_archived=True)
            d = self._new_message(session, created_at=datetime(2026, 2, 4, tzinfo=UTC))
            self._new_recipient(session, d.id, u.id, is_read=True, is_archived=True)

            svc = NotificationMessageService(session)
            combos = [
                (False, None),
                (False, "unread"),
                (False, "read"),
                (False, "archived"),
                (True, None),
                (True, "archived"),
                (True, "read"),
                (True, "unread"),
            ]
            for include_archived, read_status in combos:
                new = {
                    item["recipientId"] for item in svc.list_for_user(u.id, include_archived, read_status=read_status)
                }
                legacy = self._legacy_list(session, u.id, include_archived, read_status)
                print(
                    f"[F3 equiv] include_archived={include_archived} read_status={read_status!r}: new={new} legacy={legacy}"
                )
                self.assertEqual(new, legacy, f"组合 ({include_archived},{read_status}) 结果不一致")

    def test_f3_pagination(self):
        """D2：limit/offset 生效；默认 None 返回全部；offset=0 等价于不传。"""
        with Session(self.engine) as session:
            users = self._seed_users(session, n=1)
            u = users[0]
            rids = []
            for i in range(5):
                m = self._new_message(session, created_at=datetime(2026, 3, 1 + i, tzinfo=UTC))
                r = self._new_recipient(session, m.id, u.id, is_read=False, is_archived=False)
                rids.append(r.id)
            svc = NotificationMessageService(session)

            all_rows = svc.list_for_user(u.id)
            self.assertEqual(len(all_rows), 5, "默认（limit/offset=None）应返回全部")
            # 顺序 desc：created_at 越晚越靠前
            self.assertEqual([x["recipientId"] for x in all_rows], list(reversed(rids)))

            self.assertEqual(len(svc.list_for_user(u.id, limit=2)), 2)
            page2 = svc.list_for_user(u.id, offset=2, limit=2)
            self.assertEqual([x["recipientId"] for x in page2], [x["recipientId"] for x in all_rows[2:4]])
            # offset=0 为假值 -> 不追加 offset，语义等价于不传
            self.assertEqual(len(svc.list_for_user(u.id, offset=0)), 5, "offset=0 应等价于不传（返回全部）")
            self.assertEqual(
                [x["recipientId"] for x in svc.list_for_user(u.id, offset=0, limit=2)],
                [x["recipientId"] for x in svc.list_for_user(u.id, limit=2)],
            )

    def test_f3_controller_clamps_limit_and_offset(self):
        """D3：控制器夹取。契约已由 `int | None` 调整为 `int = 0`（0=不限制）。

        断言：默认(0,0)→全部；limit=9999→夹到 MAX_LIST_LIMIT(200)；offset<0→归 0；
        offset 正常生效。负数/0 的 limit 因 `limit or None` 语义→不限制（见 §deviation 记录）。
        """
        with Session(self.engine) as session:
            users = self._seed_users(session, n=1)
            u = users[0]
            for i in range(250):
                m = self._new_message(session, created_at=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(seconds=i))
                self._new_recipient(session, m.id, u.id, is_read=False, is_archived=False)
            ctl = NotificationMessageController()

            backward = ctl.mine(limit=0, offset=0, current_user=u, session=session)
            print(f"\n[F3 clamp] 默认(0,0) -> len={len(backward)}")
            self.assertEqual(len(backward), 250, "默认(limit=0,offset=0) 应返回全部（向后兼容）")

            clamped = ctl.mine(limit=9999, offset=0, current_user=u, session=session)
            self.assertEqual(len(clamped), 200, "limit=9999 应被夹到 MAX_LIST_LIMIT=200")

            neg = ctl.mine(limit=200, offset=-5, current_user=u, session=session)
            self.assertEqual(neg[0]["recipientId"], backward[0]["recipientId"], "offset=-5 应归 0（返回同首条）")

            paged = ctl.mine(limit=2, offset=1, current_user=u, session=session)
            self.assertEqual([x["recipientId"] for x in paged], [x["recipientId"] for x in backward[1:3]])

            # 新契约：limit<0 / limit=0 → 不限制（`limit or None`），非取 1 条
            self.assertEqual(len(ctl.mine(limit=-5, offset=0, current_user=u, session=session)), 250)

    # ---------- E. F4：停用超管 ----------
    def test_f4_super_admins_excludes_inactive(self):
        """E1/E2：active_admins / super_admins / all_admins 均只返回启用超管；停用超管不再投递。"""
        with Session(self.engine) as session:
            active_admin = User(username="sa", full_name="sa", password_hash="x", is_active=True, is_super_admin=True)
            disabled_admin = User(
                username="sd", full_name="sd", password_hash="x", is_active=False, is_super_admin=True
            )
            session.add_all([active_admin, disabled_admin])
            session.commit()
            session.refresh(active_admin)
            session.refresh(disabled_admin)

            svc = NotificationService(session)
            for cond in ("super_admins", "active_admins"):
                got = {u.id for u in svc.resolve_recipients(AudienceRule(condition=cond))}
                print(f"[F4] condition={cond!r} -> {got}")
                self.assertEqual(got, {active_admin.id}, f"{cond} 应只返回启用超管")
            all_admin = {u.id for u in svc.resolve_recipients(AudienceRule(all_admins=True))}
            self.assertEqual(all_admin, {active_admin.id}, "all_admins 行为应与改动前一致（启用超管）")

            # 旧逻辑推演：super_admins 分支只按 is_super_admin 过滤 -> 会包含停用超管
            legacy = session.exec(select(User).where(User.is_super_admin == True)).all()  # noqa: E712
            legacy_ids = {u.id for u in legacy}
            print(f"[F4] legacy super_admins -> {legacy_ids}")
            self.assertIn(disabled_admin.id, legacy_ids, "旧逻辑确实会纳入停用超管（证明修复有效性）")


if __name__ == "__main__":
    unittest.main()
