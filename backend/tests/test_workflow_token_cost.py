"""Token/Cost 运行展示（报告 #2 剩余部分）：instance 聚合 AiModelCallLog 的 token/cost。

数据层早已就绪（AiModelCallLog.workflow_instance_id），本测试覆盖 instance 列表/详情
回填的 _enrich_token_cost：按 instance 批量聚合，避免 N+1。
"""

from __future__ import annotations

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.workflow_service import WorkflowInstanceService


class EnrichTokenCostTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self):
        d = WorkflowDefinition(
            code="wf1", name="WF1", graph_json="{}", is_active=True, current_version_id=1, user_id=1
        )
        self.session.add(d)
        self.session.commit()
        self.session.refresh(d)
        return d

    def _add_instance(self, definition, thread_id="t1"):
        i = WorkflowInstance(
            definition_id=definition.id,
            thread_id=thread_id,
            status="success",
            state_data="{}",
            user_id=1,
        )
        self.session.add(i)
        self.session.commit()
        self.session.refresh(i)
        return i

    def test_aggregates_token_cost_by_instance(self):
        """_enrich_token_cost 按 instance 聚合其全部 LLM 调用的 token/cost（一次 group by）。"""
        from app.modules.ai.model.ai import AiModelCallLog

        definition = self._add_definition()
        instance = self._add_instance(definition, "t1")
        other = self._add_instance(definition, "t2")

        # instance 关联 2 条调用，other 关联 1 条
        self.session.add(AiModelCallLog(workflow_instance_id=instance.id, total_tokens=100, cost_micro_usd=500))
        self.session.add(AiModelCallLog(workflow_instance_id=instance.id, total_tokens=200, cost_micro_usd=1500))
        self.session.add(AiModelCallLog(workflow_instance_id=other.id, total_tokens=999, cost_micro_usd=999))
        self.session.commit()

        svc = WorkflowInstanceService(self.session)
        items = [{"id": instance.id}, {"id": other.id}]
        svc._enrich_token_cost(items)

        self.assertEqual(items[0]["totalTokens"], 300)  # 100 + 200
        self.assertEqual(items[0]["costUsd"], 0.002)  # (500 + 1500) / 1e6
        self.assertEqual(items[1]["totalTokens"], 999)
        self.assertEqual(items[1]["costUsd"], 0.000999)

    def test_no_logs_yields_zero(self):
        """无 LLM 调用记录的 instance，token/cost 回填为 0。"""
        definition = self._add_definition()
        instance = self._add_instance(definition, "t1")

        svc = WorkflowInstanceService(self.session)
        items = [{"id": instance.id}]
        svc._enrich_token_cost(items)

        self.assertEqual(items[0]["totalTokens"], 0)
        self.assertEqual(items[0]["costUsd"], 0.0)

    def test_empty_items_noop(self):
        """空列表不报错（page 空结果场景）。"""
        svc = WorkflowInstanceService(self.session)
        svc._enrich_token_cost([])


if __name__ == "__main__":
    unittest.main()
