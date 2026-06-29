"""Phase 3 重构验证：提取出的纯函数行为正确（_resolve_execution_graph / _parse_llm_output）。

纯重构不改行为，靠这些单元测试 + 全回归共同保证等价性。
"""

from __future__ import annotations

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.workflow_service import _parse_llm_output
from app.modules.workflow.tasks.workflow_tasks import _resolve_execution_graph


class ResolveExecutionGraphTestCase(unittest.TestCase):
    """_async_execute 提取出的编译拓扑解析（#20）。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def _add_definition(self, current_version_id=None):
        d = WorkflowDefinition(
            code="wf1",
            name="WF1",
            graph_json="{}",
            is_active=True,
            current_version_id=current_version_id,
            user_id=1,
        )
        self.session.add(d)
        self.session.commit()
        self.session.refresh(d)
        return d

    def _add_instance(self, definition, thread_id="t1", version_id=None):
        i = WorkflowInstance(
            definition_id=definition.id,
            thread_id=thread_id,
            status="running",
            state_data="{}",
            version_id=version_id,
            user_id=1,
        )
        self.session.add(i)
        self.session.commit()
        self.session.refresh(i)
        return i

    def test_override_takes_priority(self):
        """graph_json_override 优先，直接返回，不查 version。"""
        definition = self._add_definition()
        instance = self._add_instance(definition)
        override = {"nodes": [{"id": "n1"}], "edges": []}
        result = _resolve_execution_graph(self.session, instance.id, definition.id, None, override)
        self.assertIsNotNone(result)
        graph_json, thread_id = result
        self.assertEqual(graph_json, override)
        self.assertEqual(thread_id, "t1")

    def test_returns_none_when_instance_missing(self):
        definition = self._add_definition()
        result = _resolve_execution_graph(self.session, 99999, definition.id, None, None)
        self.assertIsNone(result)

    def test_returns_none_when_definition_missing(self):
        definition = self._add_definition()
        instance = self._add_instance(definition)
        result = _resolve_execution_graph(self.session, instance.id, 99999, None, None)
        self.assertIsNone(result)

    def test_returns_none_when_no_available_version(self):
        """无 override 且 version_id/instance.version_id/current_version_id 均空 → None。"""
        definition = self._add_definition(current_version_id=None)
        instance = self._add_instance(definition, version_id=None)
        result = _resolve_execution_graph(self.session, instance.id, definition.id, None, None)
        self.assertIsNone(result)


class ParseLlmOutputTestCase(unittest.TestCase):
    """execute_llm_node 提取出的输出解析（#21）。"""

    def test_plain_text_passthrough(self):
        self.assertEqual(_parse_llm_output("hello", "text", "output"), {"output": "hello"})

    def test_json_mode_parses(self):
        self.assertEqual(_parse_llm_output('{"a": 1}', "json", "out"), {"out": {"a": 1}})

    def test_json_mode_strips_markdown_fence(self):
        content = "```json\n{\"a\": 2}\n```"
        self.assertEqual(_parse_llm_output(content, "json", "out"), {"out": {"a": 2}})

    def test_json_mode_invalid_keeps_raw(self):
        """JSON 解析失败时保留原始文本。"""
        self.assertEqual(_parse_llm_output("not json", "json_object", "out"), {"out": "not json"})


if __name__ == "__main__":
    unittest.main()
