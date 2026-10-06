"""开始节点输入默认值补齐测试（B：apply_start_input_defaults）。

覆盖：
- 新写法 [{name, default}] 在输入缺失/空串/None 时回落到默认值
- 用户显式传入的值（含 0）一律优先
- 旧写法 ["name"] 与 snake_case 键名向后兼容
- 无 start 节点 / 非 dict 输入的保护
"""

from __future__ import annotations

import json
from pathlib import Path

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
    path = Path(__file__).resolve().parents[2] / "examples" / "workflows" / "13_XHS_PictureBook_Pipeline_Parametric.json"
    if not path.exists():
        return
    graph = json.loads(json.loads(path.read_text(encoding="utf-8"))["graph_json"])
    merged = apply_start_input_defaults(graph, {"input_query": "阿苏不肯刷牙"})
    assert merged["image_count"] == 10
