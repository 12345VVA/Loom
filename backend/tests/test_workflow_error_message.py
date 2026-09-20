"""工作流错误消息格式化与失败节点日志行测试。

- friendly_error_message：异常分类折叠（NodeExecutionError / HTTPException /
  UpstreamApiError / 程序性异常）、清洗与截断（替代"非 ValueError 一律内部错误"）
- _build_error_log_payload：失败节点 error 日志 payload 构造（与成功行同构）
- _persist_node_payloads_sync：error 行落库 + 成功行 ref_prev 行为回归
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.ai.service.adapters.base import UpstreamApiError
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.service.compiler import NodeExecutionError
from app.modules.workflow.service.error_format import friendly_error_message
from app.modules.workflow.tasks import workflow_tasks as wt


class FriendlyErrorMessageTestCase(unittest.TestCase):
    """异常 → 可读消息的分类折叠。"""

    def test_node_execution_error_with_node_name(self):
        """NodeExecutionError + 节点名映射 → 技术 id 替换为节点名"""
        e = NodeExecutionError("n1", 3, ValueError("余额不足"))
        msg = friendly_error_message(e, {"n1": "LLM 节点"})
        self.assertEqual(msg, "节点「LLM 节点」执行失败（已尝试 3 次）: 余额不足")

    def test_unknown_node_falls_back_to_id(self):
        e = NodeExecutionError("n_raw", 1, ValueError("x"))
        msg = friendly_error_message(e, {"other": "别的节点"})
        self.assertIn("n_raw", msg)
        self.assertNotIn("别的节点", msg)

    def test_http_exception_detail_unwrapped(self):
        """cause 为 HTTPException → 取 detail 全文，去掉 "400: " 状态码前缀"""
        e = NodeExecutionError("n1", 1, HTTPException(status_code=400, detail="模型调用失败: 超时"))
        msg = friendly_error_message(e, {"n1": "LLM 节点"})
        self.assertIn("模型调用失败: 超时", msg)
        self.assertNotIn("400", msg)

    def test_http_exception_dict_detail_serialized(self):
        """detail 为 dict（FastAPI 允许）→ JSON 序列化且中文不转义"""
        e = HTTPException(status_code=400, detail={"reason": "限流", "retry": 30})
        msg = friendly_error_message(e)
        self.assertIn('"reason": "限流"', msg)
        self.assertIn("30", msg)

    def test_upstream_api_error_with_request_id(self):
        e = UpstreamApiError("rate limited", status_code=429, request_id="req-1")
        msg = friendly_error_message(e)
        self.assertIn("rate limited", msg)
        self.assertIn("req-1", msg)

    def test_generic_exception_gets_type_prefix(self):
        """程序性异常带类型名前缀（KeyError('x') 的 str 只有引号，无类型难定位）"""
        self.assertEqual(friendly_error_message(RuntimeError("boom")), "RuntimeError: boom")
        self.assertEqual(friendly_error_message(KeyError("cfg")), "KeyError: 'cfg'")

    def test_empty_str_exception_falls_back_to_type_name(self):
        class Silent(Exception):
            __str__ = lambda self: ""  # noqa: E731

        self.assertEqual(friendly_error_message(Silent()), "Silent")

    def test_multiline_message_cleaned(self):
        e = ValueError("第一行\n第二行\t制表  \n")
        msg = friendly_error_message(e)
        self.assertNotIn("\n", msg)
        self.assertNotIn("\t", msg)
        self.assertEqual(msg, "第一行 第二行 制表")

    def test_truncated_to_max_len(self):
        e = ValueError("长" * 600)
        self.assertEqual(len(friendly_error_message(e)), 500)

    def test_blank_message_falls_back(self):
        """展开清洗后为空 → 退回兜底文案"""
        self.assertEqual(friendly_error_message(ValueError("  \n\t ")), "执行失败，发生内部错误。")

    def test_nested_node_errors_depth_bounded(self):
        """cause 也是 NodeExecutionError（人为构造）→ 深度受控不炸栈；各层均做名字映射"""
        deep = NodeExecutionError("deep", 1, RuntimeError("x"))
        mid = NodeExecutionError("mid", 1, deep)
        outer = NodeExecutionError("outer", 1, mid)
        msg = friendly_error_message(outer, {"outer": "外层", "mid": "中层", "deep": "深层"})
        self.assertIn("外层", msg)
        self.assertIn("中层", msg)
        self.assertIn("深层", msg)


class BuildErrorLogPayloadTestCase(unittest.TestCase):
    """失败节点 error 日志 payload 构造。"""

    def test_builds_full_payload_for_node_error(self):
        """payload 与成功行同构（_persist 无条件读 state_data/latency_ms）"""
        error = NodeExecutionError("n_img", 2, ValueError("生图失败"))
        nodes_map = {"n_img": {"name": "封面生图", "type": "image_generator"}}
        current_vars = {"input_query": "关于嫉妒", "plan_output": {"category": "情绪安抚"}}
        payload = wt._build_error_log_payload(error, nodes_map, current_vars)
        self.assertIsNotNone(payload)
        self.assertEqual(
            set(payload.keys()),
            {"node_id", "node_name", "node_type", "state_data", "input_data", "output_data", "latency_ms", "status", "error_message"},
        )
        self.assertEqual(payload["node_id"], "n_img")
        self.assertEqual(payload["node_name"], "封面生图")
        self.assertEqual(payload["node_type"], "image_generator")
        # state_data 是未脱敏运行时快照（与成功行一致），input 才是脱敏副本
        self.assertEqual(json.loads(payload["state_data"]), current_vars)
        self.assertEqual(json.loads(payload["input_data"])["input_query"], "关于嫉妒")
        self.assertEqual(payload["output_data"], "{}")
        self.assertEqual(payload["latency_ms"], 0)
        self.assertEqual(payload["status"], "error")
        self.assertIn("封面生图", payload["error_message"])
        self.assertIn("生图失败", payload["error_message"])

    def test_returns_none_without_node_id(self):
        """失败节点未知（超时、编译前异常等）→ None，不投递日志行"""
        self.assertIsNone(wt._build_error_log_payload(RuntimeError("boom"), {}, {}))


class PersistErrorLogTestCase(unittest.TestCase):
    """_persist_node_payloads_sync：error 行落库 + 成功行回归。"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            definition = WorkflowDefinition(
                code="wf1", name="WF1", graph_json="{}", is_active=True, current_version_id=1, user_id=1
            )
            session.add(definition)
            session.commit()
            session.refresh(definition)
            instance = WorkflowInstance(
                definition_id=definition.id, thread_id="t1", status="running", state_data="{}"
            )
            session.add(instance)
            session.commit()
            session.refresh(instance)
            self.instance_id = instance.id

    def _persist(self, payloads: list[dict]) -> None:
        with patch.object(wt, "engine", self.engine):
            wt._persist_node_payloads_sync(self.instance_id, payloads)

    def _logs(self) -> list[WorkflowExecutionLog]:
        with Session(self.engine) as session:
            return list(session.exec(_log_select()).all())

    def test_success_rows_keep_legacy_behavior(self):
        """回归：全 success payload → ref_prev/diff_base 行为不变、error_message 为空"""
        self._persist(
            [
                _success_payload("n1", '{"v": 1}'),
                _success_payload("n2", '{"v": 2}'),
            ]
        )
        logs = self._logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual([log.status for log in logs], ["success", "success"])
        self.assertIsNone(logs[0].error_message)
        self.assertEqual(logs[0].payload_type, "full")
        self.assertEqual(logs[1].payload_type, "ref_prev")
        self.assertEqual(logs[1].diff_base_log_id, logs[0].id)

    def test_error_row_persisted_and_instance_advanced(self):
        """[success, error] → error 行落库带原因，实例 current_node 推进到失败节点"""
        err_payload = wt._build_error_log_payload(
            NodeExecutionError("n_fail", 1, ValueError("模型 401")),
            {"n_fail": {"name": "总结节点", "type": "llm"}},
            {"v": 2},
        )
        self._persist([_success_payload("n1", '{"v": 1}'), err_payload])
        logs = self._logs()
        self.assertEqual([log.status for log in logs], ["success", "error"])
        self.assertEqual(logs[1].node_name, "总结节点")
        self.assertIn("模型 401", logs[1].error_message)
        with Session(self.engine) as session:
            inst = session.get(WorkflowInstance, self.instance_id)
            self.assertEqual(inst.current_node, "n_fail")
            self.assertEqual(json.loads(inst.state_data), {"v": 2})

    def test_error_first_row_uses_full_payload(self):
        """首节点即失败 → 无前序日志，input 走 full 而非 ref_prev"""
        err_payload = wt._build_error_log_payload(
            NodeExecutionError("n_first", 1, ValueError("输入缺失")),
            {"n_first": {"name": "入口", "type": "llm"}},
            {"q": "hello"},
        )
        self._persist([err_payload])
        logs = self._logs()
        self.assertEqual(logs[0].payload_type, "full")
        self.assertIsNone(logs[0].diff_base_log_id)
        self.assertIn("q", logs[0].input_data)

    def test_legacy_payload_without_new_keys_defaults_success(self):
        """旧调用形态（payload 无 status/error_message key）→ 默认 success，行为不变"""
        self._persist(
            [
                {
                    "node_id": "n1",
                    "node_name": "N1",
                    "node_type": "llm",
                    "state_data": "{}",
                    "input_data": "{}",
                    "output_data": "{}",
                    "latency_ms": 5,
                }
            ]
        )
        logs = self._logs()
        self.assertEqual(logs[0].status, "success")
        self.assertIsNone(logs[0].error_message)


def _success_payload(node_id: str, state_data: str) -> dict:
    return {
        "node_id": node_id,
        "node_name": node_id.upper(),
        "node_type": "llm",
        "state_data": state_data,
        "input_data": "{}",
        "output_data": "{}",
        "latency_ms": 10,
    }


def _log_select():
    from sqlmodel import select

    return select(WorkflowExecutionLog).order_by(WorkflowExecutionLog.id)


if __name__ == "__main__":
    unittest.main()
