"""节点元数据 manifest 单一来源导出与校验（三期B7 / WF-P2-7）。

后端为节点元数据唯一权威（注册表 + graph_validate 常量集），本脚本生成前端
TS 产物，替代 constants.ts 的手写镜像与分散的后端注释（防漂移）：
- 生成/更新：cd backend && python scripts/dump_node_manifest.py
- 校验（CI 用）：python scripts/dump_node_manifest.py --check，不一致退出码 1

产物：frontend/src/modules/workflow/generated/node-manifest.ts（入库）。
一致性守卫：backend/tests/test_workflow_untestable_sync.py 比对产物与后端权威。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import app.modules.workflow.service.node_executors  # noqa: E402,F401  import 副作用完成注册
from app.modules.workflow.service.graph_validate import (  # noqa: E402
    CONDITIONAL_NODE_TYPES,
    INTERRUPT_NODE_TYPES,
    MOCK_TOOL_CODES,
    SUBGRAPH_NODE_TYPES,
    UNTESTABLE_NODE_TYPES,
)
from app.modules.workflow.service.node_schema import NODE_OUTPUT_VAR_DEFAULTS  # noqa: E402
from app.modules.workflow.service.state import node_registry  # noqa: E402

MANIFEST_PATH = BACKEND_ROOT.parent / "frontend" / "src" / "modules" / "workflow" / "generated" / "node-manifest.ts"

HEADER = """\
// 由 backend/scripts/dump_node_manifest.py 生成，勿手改。
// 再生成：cd backend && python scripts/dump_node_manifest.py
// 权威来源：node_executors 注册表（idempotent/deprecated）+ graph_validate 常量集
// + node_schema.NODE_OUTPUT_VAR_DEFAULTS（输出变量默认名，WF-P2-8）；
// 守卫：backend/tests/test_workflow_untestable_sync.py 比对产物与后端。

export interface NodeManifestEntry {
\ttype: string;
\tuntestable: boolean;
\tinterrupt: boolean;
\tsubgraph: boolean;
\tconditional: boolean;
\tidempotent: boolean;
\tdeprecated: boolean;
\toutputVarDefault: string | null;
}

"""


def _ts_str_set(values: set[str] | frozenset[str]) -> str:
    return "[" + ", ".join(f"'{v}'" for v in sorted(values)) + "]"


def render() -> str:
    lines = [HEADER]
    lines.append("export const NODE_MANIFEST: readonly NodeManifestEntry[] = [\n")
    for node_type in sorted(node_registry.types()):
        ovd_val = NODE_OUTPUT_VAR_DEFAULTS.get(node_type)
        entry = (
            "\t{{ type: '{t}', untestable: {u}, interrupt: {i}, subgraph: {s}, "
            "conditional: {c}, idempotent: {idem}, deprecated: {dep}, "
            "outputVarDefault: {ovd} }},\n"
        ).format(
            t=node_type,
            u=str(node_type in UNTESTABLE_NODE_TYPES).lower(),
            i=str(node_type in INTERRUPT_NODE_TYPES).lower(),
            s=str(node_type in SUBGRAPH_NODE_TYPES).lower(),
            c=str(node_type in CONDITIONAL_NODE_TYPES).lower(),
            idem=str(node_registry.is_idempotent(node_type)).lower(),
            dep=str(node_registry.is_deprecated(node_type)).lower(),
            ovd="null" if ovd_val is None else f"'{ovd_val}'",
        )
        lines.append(entry)
    lines.append("] as const;\n\n")
    lines.append(f"export const UNTESTABLE_NODE_TYPES: readonly string[] = {_ts_str_set(UNTESTABLE_NODE_TYPES)};\n\n")
    lines.append(f"export const INTERRUPT_NODE_TYPES: readonly string[] = {_ts_str_set(INTERRUPT_NODE_TYPES)};\n\n")
    lines.append(f"export const SUBGRAPH_NODE_TYPES: readonly string[] = {_ts_str_set(SUBGRAPH_NODE_TYPES)};\n\n")
    lines.append(f"export const CONDITIONAL_NODE_TYPES: readonly string[] = {_ts_str_set(CONDITIONAL_NODE_TYPES)};\n\n")
    lines.append(f"export const MOCK_TOOL_CODES: readonly string[] = {_ts_str_set(MOCK_TOOL_CODES)};\n")
    return "".join(lines)


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if not MANIFEST_PATH.exists():
            print(f"FAIL: 产物不存在，请运行 python scripts/dump_node_manifest.py 生成: {MANIFEST_PATH}")
            return 1
        if MANIFEST_PATH.read_text(encoding="utf-8") != content:
            print("FAIL: 节点元数据与前端 manifest 产物不一致——节点注册表/常量集已变更。")
            print("处理：python scripts/dump_node_manifest.py 重新生成并一并提交。")
            return 1
        print(f"OK: 节点元数据 manifest 一致（{len(node_registry.types())} 个节点类型）")
        return 0

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"节点 manifest 已写入 {MANIFEST_PATH}（{len(node_registry.types())} 个节点类型）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
