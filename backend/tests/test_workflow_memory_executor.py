"""memory_store 执行器单测（设计 §6.1 / §8 门控 / §9.1 归属边界）。

在 backend/ 目录下运行：
    cd backend && venv\\Scripts\\python.exe -m pytest tests/test_workflow_memory_executor.py -q
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.core.database import SessionLocal as real_session_local  # noqa: F401 patch 锚点
from app.core.logging import workflow_instance_id_ctx
from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.model.workflow_memory import WorkflowMemory
from app.modules.workflow.service import workflow_memory_service as wms
from app.modules.workflow.service.node_executors import execute_memory_store_node


class MemoryStoreExecutorTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.definition = WorkflowDefinition(
            code="wf1", name="WF1", is_active=True, user_id=1, memory_write_enabled=True
        )
        self.session.add(self.definition)
        self.session.commit()
        self.session.refresh(self.definition)
        self.instance = WorkflowInstance(
            definition_id=self.definition.id,
            thread_id="t1",
            status="running",
            state_data="{}",
            run_type="production",
            user_id=7,
        )
        self.session.add(self.instance)
        self.session.commit()
        self.session.refresh(self.instance)
        # 执行器内 SessionLocal 均函数内 import 自 app.core.database——patch 指向测试引擎
        self._session_local_patcher = patch("app.core.database.SessionLocal", lambda: Session(self.engine))
        self._session_local_patcher.start()
        self._ctx_token = workflow_instance_id_ctx.set(self.instance.id)

    def tearDown(self):
        if self._ctx_token is not None:
            workflow_instance_id_ctx.reset(self._ctx_token)
        self._session_local_patcher.stop()
        self.session.close()
        self.engine.dispose()

    def _run(self, variables=None, **config):
        config.setdefault("content_template", "记住 {fact}")
        variables = variables if variables is not None else {"fact": "客户A报价8折"}
        return asyncio.run(execute_memory_store_node(variables, config))

    def _rows(self):
        return list(self.session.exec(select(WorkflowMemory)).all())

    # ---------- 归属边界 ----------

    def test_attribution_from_context_not_variables(self):
        """归属恒自运行时上下文：variables 伪造 definitionId 无效（§9.1 安全边界）。"""
        self._run(variables={"fact": "x", "definitionId": 999})
        row = self._rows()[0]
        self.assertEqual(row.definition_id, self.definition.id)  # 来自 instance，非 variables
        self.assertEqual(row.source_instance_id, self.instance.id)
        self.assertEqual(row.created_by_user_id, 7)  # instance.user_id

    def test_missing_context_rejected(self):
        """ctx 缺失（直调执行器）→ 拒绝，不猜测归属。"""
        workflow_instance_id_ctx.reset(self._ctx_token)
        self._ctx_token = None  # 已手动重置，tearDown 跳过
        with self.assertRaises(ValueError):
            self._run()

    # ---------- 写权限 ----------

    def test_write_disabled_fails(self):
        self.definition.memory_write_enabled = False
        self.session.add(self.definition)
        self.session.commit()
        with self.assertRaises(ValueError) as ctx:
            self._run()
        self.assertIn("memoryWriteEnabled", str(ctx.exception))

    # ---------- env 门控 ----------

    def test_eval_skipped(self):
        self.instance.run_type = "eval"
        self.session.add(self.instance)
        self.session.commit()
        result = self._run()
        self.assertEqual(result, {"memory_id": None, "memory_action": "skipped"})
        self.assertEqual(self._rows(), [])

    def test_test_node_writes_test_env(self):
        self.instance.run_type = "test_node"
        self.session.add(self.instance)
        self.session.commit()
        result = self._run()
        self.assertEqual(result["memory_action"], "created")
        row = self._rows()[0]
        self.assertEqual(row.memory_env, "test")
        self.assertEqual(row.source_run_type, "test_node")

    def test_trial_writes_production_env(self):
        """trial 有意写 production（试运行必须真实反映节点语义），溯源 trial。"""
        self.instance.run_type = "trial"
        self.session.add(self.instance)
        self.session.commit()
        result = self._run()
        self.assertEqual(result["memory_action"], "created")
        row = self._rows()[0]
        self.assertEqual(row.memory_env, "production")
        self.assertEqual(row.source_run_type, "trial")

    # ---------- 内容校验 ----------

    def test_empty_render_rejected(self):
        """模板渲染后为空（strip 后）→ fail-fast 拒绝写空记忆。"""
        with self.assertRaises(ValueError):
            self._run(variables={"fact": "   "}, content_template="{fact}")

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            self._run(variables={"fact": "长" * 5000})

    def test_credential_warning_but_written(self):
        """凭据模式命中仅 warning 不阻断（讨论密钥管理是合法内容）——
        warning 由执行器模块 logger 发出。"""
        with self.assertLogs("app.modules.workflow.service.node_executors", level="WARNING"):
            result = self._run(variables={"fact": "sk-proj-abc123def456ghi789jkl"})
        self.assertEqual(result["memory_action"], "created")

    # ---------- embedding 三态 ----------

    def test_embedding_failure_degrades_to_null_with_bare_code(self):
        """embedding 调用失败 → 行落库 embedding=NULL + space=裸 code（§4.5 失败态）。"""
        with patch.object(wms, "run_ai_embedding", return_value=(None, "text-embedding-v3")):
            result = self._run()
        self.assertEqual(result["memory_action"], "created")
        row = self._rows()[0]
        self.assertIsNone(row.embedding)
        self.assertEqual(row.embedding_space, "text-embedding-v3")  # 裸 code，无维度段

    def test_embedding_ready(self):
        with patch.object(wms, "run_ai_embedding", return_value=([0.1, 0.2], "text-embedding-v3:2")):
            self._run()
        row = self._rows()[0]
        self.assertEqual(row.embedding_space, "text-embedding-v3:2")

    # ---------- 错误口径 ----------

    def test_db_failure_raises_by_default(self):
        with patch.object(wms, "upsert_memory", side_effect=RuntimeError("db down")):
            with self.assertRaises(ValueError):
                self._run()

    def test_on_error_degrade_returns_marker(self):
        with patch.object(wms, "upsert_memory", side_effect=RuntimeError("db down")):
            result = self._run(on_error="degrade")
        self.assertEqual(result, {"memory_id": None, "memory_action": "degraded"})

    # ---------- 输出契约 ----------

    def test_memory_action_and_custom_output_variable(self):
        result = self._run(output_variable="saved_id", memory_key_template="customer:{fact}:policy")
        self.assertEqual(result["memory_action"], "created")
        self.assertTrue(result["saved_id"] > 0)
        row = self._rows()[0]
        self.assertEqual(row.memory_key, "customer:客户A报价8折:policy")  # 业务身份模板渲染

    def test_key_upsert_via_executor(self):
        r1 = self._run(memory_key_template="k:{fact}")
        r2 = self._run(memory_key_template="k:{fact}")
        self.assertEqual(r1["memory_action"], "created")
        self.assertEqual(r2["memory_action"], "updated")
        self.assertEqual(r1["memory_id"], r2["memory_id"])
        self.assertEqual(len(self._rows()), 1)


if __name__ == "__main__":
    unittest.main()
