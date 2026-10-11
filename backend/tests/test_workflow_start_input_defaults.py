"""开始节点输入默认值补齐测试（B：apply_start_input_defaults）。

覆盖：
- 新写法 [{name, default}] 在输入缺失/空串/None 时回落到默认值
- 用户显式传入的值（含 0）一律优先
- 旧写法 ["name"] 与 snake_case 键名向后兼容
- 无 start 节点 / 非 dict 输入的保护
- 入口 Base64 防线（WFI-1a）：data URI 输入在 start/trial/test_node 三入口被拒绝
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

import pytest
from fastapi import HTTPException
from helpers import make_test_engine
from sqlmodel import Session, SQLModel, select

from app.modules.workflow.model.workflow import WorkflowDefinition, WorkflowInstance
from app.modules.workflow.service.workflow_service import (
    WorkflowInstanceService,
    _reject_inline_data_uris,
)
from app.modules.workflow.tasks.workflow_tasks import apply_start_input_defaults


def _graph(input_variables: object, key: str = "inputVariables") -> dict:
    return {"nodes": [{"id": "node_start", "type": "start", "config": {key: input_variables}}]}


def test_object_form_applies_default_on_missing_and_blank():
    g = _graph([{"name": "input_query"}, {"name": "image_count", "default": 10}])
    assert apply_start_input_defaults(g, {"input_query": "阿苏不肯刷牙"}) == {
        "input_query": "阿苏不肯刷牙",
        "image_count": 10,
    }
    assert apply_start_input_defaults(g, {"input_query": "x", "image_count": ""})["image_count"] == 10
    assert apply_start_input_defaults(g, {"input_query": "x", "image_count": None})["image_count"] == 10
    assert apply_start_input_defaults(g, {"input_query": "x", "image_count": "   "})["image_count"] == 10


def test_explicit_value_wins_including_zero():
    g = _graph([{"name": "image_count", "default": 10}])
    assert apply_start_input_defaults(g, {"image_count": 6})["image_count"] == 6
    assert apply_start_input_defaults(g, {"image_count": "8"})["image_count"] == "8"
    assert apply_start_input_defaults(g, {"image_count": 0})["image_count"] == 0
    assert apply_start_input_defaults(g, {"image_count": "0"})["image_count"] == "0"


def test_no_default_declared_keeps_inputs_untouched():
    g = _graph(["input_query"])
    assert apply_start_input_defaults(g, {"input_query": "x"}) == {"input_query": "x"}
    assert apply_start_input_defaults(g, {}) == {}  # 未声明默认值的变量不会被凭空加入


def test_snake_case_key_and_defensive_paths():
    assert apply_start_input_defaults(_graph([{"name": "n", "default": 7}], key="input_variables"), {}) == {"n": 7}
    assert apply_start_input_defaults({"nodes": []}, {"a": 1}) == {"a": 1}
    assert apply_start_input_defaults({}, {"a": 1}) == {"a": 1}
    assert apply_start_input_defaults(_graph(["a"]), None) is None  # type: ignore[arg-type]


def test_unknown_keys_preserved():
    g = _graph([{"name": "image_count", "default": 10}])
    assert apply_start_input_defaults(g, {"image_count": 9, "other": "keep"}) == {
        "image_count": 9,
        "other": "keep",
    }


def test_packaged_workflow_13_declares_default_10():
    """随仓库分发的参数化绘本工作流：start 声明 image_count 默认 10。"""
    path = (
        Path(__file__).resolve().parents[2] / "examples" / "workflows" / "13_XHS_PictureBook_Pipeline_Parametric.json"
    )
    if not path.exists():
        return
    graph = json.loads(json.loads(path.read_text(encoding="utf-8"))["graph_json"])
    merged = apply_start_input_defaults(graph, {"input_query": "阿苏不肯刷牙"})
    assert merged["image_count"] == 10


# ---------------------------------------------------------------------------
# WFI-1a：入口 Base64 防线
# ---------------------------------------------------------------------------

_DATA_URI = "data:image/png;base64,iVBORw0KGgo="


def test_reject_inline_data_uris_function_levels():
    # 纯文本 / URL / 空输入放行
    _reject_inline_data_uris({"q": "文本", "img": "/uploads/a.png", "u": "https://x/1.jpg"})
    _reject_inline_data_uris({})
    _reject_inline_data_uris(None)  # type: ignore[arg-type]

    # str 形态拒绝，detail 指明变量名与出路
    with pytest.raises(HTTPException) as ctx:
        _reject_inline_data_uris({"input_image": _DATA_URI})
    assert "input_image" in ctx.value.detail
    assert "上传" in ctx.value.detail

    # list 形态：混在数组里的 data URI 同样拒绝
    with pytest.raises(HTTPException):
        _reject_inline_data_uris({"imgs": ["https://x/1.jpg", _DATA_URI]})

    # 非 str / 非 list 值不炸（数字、对象等）
    _reject_inline_data_uris({"n": 10, "o": {"k": "v"}})


class StartInputDataUriGuardTest(unittest.TestCase):
    """三入口（start / trial / test_node）对 data URI 输入统一 400，且不落实例。"""

    def setUp(self):
        self.engine = make_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.definition = WorkflowDefinition(
            code="wf-data-uri", name="WF", graph_json="{}", is_active=True, current_version_id=1, draft_version_id=1
        )
        self.session.add(self.definition)
        self.session.commit()
        self.session.refresh(self.definition)
        self.service = WorkflowInstanceService(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _assert_no_instance(self):
        self.assertEqual(len(self.session.exec(select(WorkflowInstance)).all()), 0)

    def test_start_rejects_data_uri_input(self):
        with pytest.raises(HTTPException) as ctx:
            self.service.start_instance(self.definition.id, {"input_image": _DATA_URI})
        self.assertEqual(ctx.value.status_code, 400)
        self._assert_no_instance()

    def test_trial_rejects_data_uri(self):
        with pytest.raises(HTTPException) as ctx:
            self.service.start_trial_instance(self.definition.id, {"img": _DATA_URI})
        self.assertEqual(ctx.value.status_code, 400)
        self._assert_no_instance()

    def test_start_rejects_data_uri_in_list(self):
        with pytest.raises(HTTPException):
            self.service.start_instance(self.definition.id, {"imgs": ["https://x/1.jpg", _DATA_URI]})
        self._assert_no_instance()

    def test_node_test_rejects_data_uri(self):
        with pytest.raises(HTTPException) as ctx:
            asyncio.run(self.service.test_node(self.definition.id, "node_x", {"img": _DATA_URI}))
        self.assertEqual(ctx.value.status_code, 400)
        self._assert_no_instance()
