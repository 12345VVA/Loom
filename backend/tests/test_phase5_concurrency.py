"""Phase 5 并发与状态机修复测试。

- 5.1 (P0-16): task.dispatch_due_tasks Redis SETNX 分布式锁
  - 锁竞争时跳过派发（不调用 execute_system_task.delay）
  - 锁获取成功时正常派发并在结束后释放锁
  - Redis 不可用时降级为无锁派发，不阻断
  - P1-B1: 锁 value 使用唯一 token + Lua 原子校验删除，避免误删其他 worker 的锁
- 5.2 (P0-17): AI Governance _acquire_concurrent fail-closed
  - enforce 模式 + Redis 故障 → 抛 AiGovernanceUnavailable（调用方映射 503）
  - monitor 模式 + Redis 故障 → fail-open 放行
  - enforce 模式 + Redis 正常 + 超限 → 抛 AiGovernanceBlocked（映射 429，回归保护）
- 5.4 (P1-5): Celery acks_late + soft_time_limit 配置生效
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import redis
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.celery_app import celery_app
from app.modules.ai.model.ai import AiGovernanceRule, AiModel, AiModelProfile, AiProvider
from app.modules.ai.service.governance_service import (
    AiGovernanceBlocked,
    AiGovernanceService,
    AiGovernanceUnavailable,
)
from app.modules.task.model.task import TaskInfo
from app.modules.task.tasks import system_tasks
from app.modules.task.tasks.system_tasks import _DISPATCH_LOCK_KEY, _RELEASE_LOCK_SCRIPT


# ==========================================
# 5.1：dispatch_due_tasks Redis SETNX 分布式锁
# ==========================================


class _FakeRedis:
    """模拟 Redis SETNX + Lua 释放锁语义，用于验证 token 匹配/不匹配场景（P1-B1）。"""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.eval_calls: list[tuple] = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def eval(self, script, numkeys, *args):
        # 模拟 _RELEASE_LOCK_SCRIPT 的原子校验后删除语义
        self.eval_calls.append((script, numkeys, args))
        key = args[0]
        token = args[1] if len(args) > 1 else None
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


class DispatchDueTasksLockTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_due_task(self) -> TaskInfo:
        task = TaskInfo(
            name="t1",
            status=1,
            service="some.service.method",
            next_run_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            cron="*/5 * * * *",
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def test_lock_contended_skips_dispatch(self):
        """锁已被其他 worker 持有时，跳过本次派发，不调用 execute_system_task.delay。"""
        self._add_due_task()
        with patch("app.core.redis.redis_client") as rc, \
                patch.object(system_tasks, "engine", self.engine), \
                patch.object(system_tasks, "execute_system_task") as exec_mock, \
                patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                patch.object(system_tasks, "record_metric_event"):
            rc.set.return_value = False  # SETNX 失败：锁竞争
            result = system_tasks.dispatch_due_tasks()

        rc.set.assert_called_once()
        # nx=True, ex=60 应在调用参数中
        _, kwargs = rc.set.call_args
        self.assertTrue(kwargs.get("nx"))
        self.assertEqual(kwargs.get("ex"), 60)
        exec_mock.delay.assert_not_called()
        # 锁竞争时早返回，不进入 try/finally，不应调用 eval
        rc.eval.assert_not_called()
        rc.delete.assert_not_called()
        self.assertEqual(result.get("skipped"), "lock_contended")
        self.assertEqual(result.get("dispatched"), [])

    def test_lock_acquired_dispatches_and_releases(self):
        """锁获取成功时正常派发，并在结束后用 Lua 脚本释放锁（token 匹配）。"""
        task = self._add_due_task()
        with patch("app.core.redis.redis_client") as rc, \
                patch.object(system_tasks, "engine", self.engine), \
                patch.object(system_tasks, "execute_system_task") as exec_mock, \
                patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                patch.object(system_tasks, "record_metric_event"):
            rc.set.return_value = True  # SETNX 成功
            result = system_tasks.dispatch_due_tasks()

        rc.set.assert_called_once()
        # 锁 value 应为唯一 token（不再是 "1"）
        set_args, set_kwargs = rc.set.call_args
        # set(KEY, token, nx=True, ex=60)：token 是第二个位置参数
        self.assertEqual(set_args[0], _DISPATCH_LOCK_KEY)
        set_token = set_args[1]
        self.assertNotEqual(set_token, "1")
        self.assertTrue(set_kwargs.get("nx"))
        self.assertEqual(set_kwargs.get("ex"), 60)

        # finally 中应通过 Lua 脚本（eval）释放锁，而非无条件 delete
        rc.eval.assert_called_once()
        rc.delete.assert_not_called()
        eval_args, _ = rc.eval.call_args
        self.assertEqual(eval_args[0], _RELEASE_LOCK_SCRIPT)
        self.assertEqual(eval_args[1], 1)  # numkeys
        self.assertEqual(eval_args[2], _DISPATCH_LOCK_KEY)
        # 释放时使用的 token 应与获取时一致
        self.assertEqual(eval_args[3], set_token)

        exec_mock.delay.assert_called_once_with(task.id)
        self.assertIn(task.id, result["dispatched"])
        self.assertTrue(result["success"])

    def test_redis_unavailable_falls_back_to_unlocked_dispatch(self):
        """Redis 不可用时降级为无锁派发，不阻断正常流程，且 finally 中跳过锁释放。"""
        task = self._add_due_task()
        with patch("app.core.redis.redis_client") as rc, \
                patch.object(system_tasks, "engine", self.engine), \
                patch.object(system_tasks, "execute_system_task") as exec_mock, \
                patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                patch.object(system_tasks, "record_metric_event"):
            rc.set.side_effect = redis.exceptions.ConnectionError("no redis")
            result = system_tasks.dispatch_due_tasks()

        rc.set.assert_called_once()
        # 降级路径未实际获取锁，finally 中不应调用 eval/delete
        rc.eval.assert_not_called()
        rc.delete.assert_not_called()
        exec_mock.delay.assert_called_once_with(task.id)  # 降级仍派发
        self.assertTrue(result["success"])

    def test_lock_release_with_matching_token_deletes_lock(self):
        """P1-B1: token 匹配时 Lua 脚本正常删除锁（worker A 释放自己持有的锁）。"""
        fake_redis = _FakeRedis()
        task = self._add_due_task()
        with patch("app.core.redis.redis_client", fake_redis), \
                patch.object(system_tasks, "engine", self.engine), \
                patch.object(system_tasks, "execute_system_task") as exec_mock, \
                patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                patch.object(system_tasks, "record_metric_event"):
            result = system_tasks.dispatch_due_tasks()

        # 锁已被 worker A 自己释放（token 匹配）
        self.assertNotIn(_DISPATCH_LOCK_KEY, fake_redis.store)
        # eval 被调用一次，返回 1（删除成功）
        self.assertEqual(len(fake_redis.eval_calls), 1)
        script, numkeys, args = fake_redis.eval_calls[0]
        self.assertEqual(script, _RELEASE_LOCK_SCRIPT)
        self.assertEqual(numkeys, 1)
        self.assertEqual(args[0], _DISPATCH_LOCK_KEY)
        exec_mock.delay.assert_called_once_with(task.id)
        self.assertTrue(result["success"])

    def test_lock_release_with_mismatched_token_preserves_other_worker_lock(self):
        """P1-B1: token 不匹配时 Lua 脚本不删除锁（worker A 误删 worker B 的锁被阻止）。

        模拟场景：worker A 持锁超过 TTL 后锁自动过期，worker B 抢到新锁（token B），
        worker A 在 finally 中用旧 token A 释放 → Lua 脚本校验失败，不删除 worker B 的锁。
        """
        fake_redis = _FakeRedis()
        task = self._add_due_task()
        worker_b_token = "worker-b-uuid-token"

        def simulate_worker_b_acquires_lock_after_ttl(*args, **kwargs):
            # 在派发过程中模拟：worker A 持锁超过 TTL，worker B 抢到新锁
            fake_redis.store[_DISPATCH_LOCK_KEY] = worker_b_token

        with patch("app.core.redis.redis_client", fake_redis), \
                patch.object(system_tasks, "engine", self.engine), \
                patch.object(system_tasks, "execute_system_task") as exec_mock, \
                patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                patch.object(system_tasks, "record_metric_event"):
            # execute_system_task.delay 触发时模拟 worker B 抢占
            exec_mock.delay.side_effect = simulate_worker_b_acquires_lock_after_ttl
            result = system_tasks.dispatch_due_tasks()

        # worker A 的 token 与 worker B 的不匹配，锁未被删除，仍持有 worker B 的 token
        self.assertEqual(fake_redis.store.get(_DISPATCH_LOCK_KEY), worker_b_token)
        # eval 仍被调用一次（worker A 尝试释放），但因 token 不匹配返回 0
        self.assertEqual(len(fake_redis.eval_calls), 1)
        script, numkeys, args = fake_redis.eval_calls[0]
        self.assertEqual(script, _RELEASE_LOCK_SCRIPT)
        self.assertEqual(args[0], _DISPATCH_LOCK_KEY)
        # worker A 使用的 token 不等于 worker B 的 token
        self.assertNotEqual(args[1], worker_b_token)
        exec_mock.delay.assert_called_once_with(task.id)
        self.assertTrue(result["success"])

    def test_lock_token_is_unique_uuid_per_dispatch(self):
        """P1-B1: 每次派发生成的 lock token 是唯一的 UUID，确保不同 worker 不会用相同 token。"""
        tokens: list[str] = []
        fake_redis = _FakeRedis()

        original_set = fake_redis.set

        def capture_token(key, value, nx=False, ex=None):
            tokens.append(value)
            return original_set(key, value, nx=nx, ex=ex)

        fake_redis.set = capture_token

        for _ in range(3):
            self._add_due_task()
            with patch("app.core.redis.redis_client", fake_redis), \
                    patch.object(system_tasks, "engine", self.engine), \
                    patch.object(system_tasks, "execute_system_task"), \
                    patch.object(system_tasks, "compute_next_run_time", return_value=datetime.now(timezone.utc) + timedelta(minutes=5)), \
                    patch.object(system_tasks, "record_metric_event"):
                system_tasks.dispatch_due_tasks()
            # 每次派发后锁应被释放，便于下一次重新获取
            fake_redis.store.pop(_DISPATCH_LOCK_KEY, None)

        self.assertEqual(len(tokens), 3)
        self.assertEqual(len(set(tokens)), 3)  # 三个 token 互不相同
        # 每个 token 应为合法 UUID 格式
        import uuid as _uuid
        for t in tokens:
            _uuid.UUID(t)  # 解析失败会抛 ValueError


# ==========================================
# 5.2：_acquire_concurrent fail-closed
# ==========================================


class AcquireConcurrentFailClosedTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_provider_model_profile(self):
        provider = AiProvider(code="p1", name="P1", base_url="http://x")
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)

        model = AiModel(provider_id=provider.id, code="m1", name="M1")
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)

        profile = AiModelProfile(code="pf1", name="PF1", model_id=model.id)
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return provider, model, profile

    def _add_rule(self, *, mode: str = "enforce", max_concurrent: int = 5) -> AiGovernanceRule:
        rule = AiGovernanceRule(
            code="r1",
            name="R1",
            scope_type="global",
            mode=mode,
            max_concurrent=max_concurrent,
            is_active=True,
            notify_enabled=False,
        )
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def test_enforce_redis_failure_raises_unavailable(self):
        """enforce 模式（cost 类规则）+ Redis 故障 → 抛 AiGovernanceUnavailable（映射 503）。"""
        rule = self._add_rule(mode="enforce", max_concurrent=5)
        provider, model, profile = self._add_provider_model_profile()
        svc = AiGovernanceService(self.session)

        with patch("app.modules.ai.service.governance_service.cache_incr", return_value=None):
            with self.assertRaises(AiGovernanceUnavailable) as cm:
                svc._acquire_concurrent([rule], None, provider, model, profile)

        self.assertIn("Redis", str(cm.exception))
        self.assertIn("R1", str(cm.exception))

    def test_monitor_redis_failure_fail_open(self):
        """monitor 模式 + Redis 故障 → fail-open 放行（不抛异常，返回空 key 列表）。"""
        rule = self._add_rule(mode="monitor", max_concurrent=5)
        provider, model, profile = self._add_provider_model_profile()
        svc = AiGovernanceService(self.session)

        with patch("app.modules.ai.service.governance_service.cache_incr", return_value=None):
            keys = svc._acquire_concurrent([rule], None, provider, model, profile)

        self.assertEqual(keys, [])

    def test_enforce_concurrent_exceed_raises_blocked(self):
        """enforce 模式 + Redis 正常 + 超限 → AiGovernanceBlocked（映射 429，回归保护）。"""
        rule = self._add_rule(mode="enforce", max_concurrent=1)
        provider, model, profile = self._add_provider_model_profile()
        svc = AiGovernanceService(self.session)

        with patch("app.modules.ai.service.governance_service.cache_incr", return_value=2), \
                patch("app.modules.ai.service.governance_service.cache_decr", return_value=1):
            with self.assertRaises(AiGovernanceBlocked):
                svc._acquire_concurrent([rule], None, provider, model, profile)


# ==========================================
# 5.4：Celery acks_late + soft_time_limit 配置
# ==========================================


class CeleryAcksLateConfigTestCase(unittest.TestCase):
    def test_acks_late_enabled(self):
        self.assertTrue(celery_app.conf.task_acks_late)

    def test_reject_on_worker_lost_enabled(self):
        self.assertTrue(celery_app.conf.task_reject_on_worker_lost)

    def test_soft_time_limit_is_25_minutes(self):
        self.assertEqual(celery_app.conf.task_soft_time_limit, 25 * 60)

    def test_hard_time_limit_still_30_minutes(self):
        """硬超时保持 30 分钟，软超时早 5 分钟触发优雅收尾。"""
        self.assertEqual(celery_app.conf.task_time_limit, 30 * 60)
        self.assertLess(celery_app.conf.task_soft_time_limit, celery_app.conf.task_time_limit)


if __name__ == "__main__":
    unittest.main()
