"""
工作流图拓扑校验（由 compiler.py 门面 re-export）。

validate_graph 在编译前验证图完整性与防错；子图体节点定位辅助函数供校验与编译共用；
存量图加载迁移（deprecated tool → tool_executor）也在此模块。
"""

import collections
import logging
from typing import Any

from app.modules.workflow.service.expressions import convert_keys_to_snake
from app.modules.workflow.service.node_schema import validate_node_config

logger = logging.getLogger(__name__)

# 条件分流节点类型集合：这些节点的出边由运行时条件路由决定，不参与静态边处理和环检测
CONDITIONAL_NODE_TYPES = {"condition", "intent_classifier", "switch"}

# 子图执行节点类型：循环体在编译时提取为独立子图，运行时按序/并发调用
SUBGRAPH_NODE_TYPES = {"loop_controller", "batch_processor"}

# 不支持单节点测试的节点类型集合（无执行逻辑、依赖子图、或需人工交互）。
# ⚠️ 本集合为权威来源；前端镜像在 frontend/src/modules/workflow/components/constants.ts，
# 改动任一侧必须同步另一侧（后端在此兜底 400，前端用于提前禁用测试入口）。
UNTESTABLE_NODE_TYPES = {"start", "end", "loop_controller", "batch_processor", "human_input", "loop_body_group"}

# 中断类节点类型：依赖 LangGraph interrupt + checkpointer 断点续跑的节点。
# 当前唯一 interrupt 源是 human_input（node_executors.execute_human_input_node）；
# 图内不含这类节点时执行全程无断点需求，可跳过 checkpointer（省 O(N²) checkpoint 写放大）。
INTERRUPT_NODE_TYPES = {"human_input"}

# Mock 占位工具集合（WF-P0-2）：tool_executor 的这三个内置 tool_code 为演示实现，
# 非 DEBUG 环境执行直接失败（见 node_executors.execute_tool_executor_node），
# 杜绝演示数据以 success 流入下游与产物。
# ⚠️ 前端不再手写镜像：由 scripts/dump_node_manifest.py 生成产物下发（三期B7），
# 守卫见 tests/test_workflow_untestable_sync.py。
MOCK_TOOL_CODES = {"web_search", "file_system", "mock_weather_api"}

# deprecated `tool` 节点已下架（三期B7 / WF-P2-10）：正常加载路径经
# migrate_legacy_tool_nodes 自动迁移为 tool_executor；绕过加载入口直造 graph_json
# 的由 validate_graph 显式拒绝。
LEGACY_TOOL_NODE_TYPE = "tool"


def migrate_legacy_tool_nodes(graph_json: dict[str, Any]) -> dict[str, Any]:
    """存量图 deprecated `tool` 节点自动迁移为 `tool_executor`（三期B7 / WF-P2-10）。

    在图加载入口（执行/试运行/编辑器草稿回填/单节点测试）统一执行，旧图无感升级：
    config 映射 tool_name→toolCode、output_variable→outputVariable；mock_data 无
    真实执行语义，迁移时丢弃并告警（tool 在生产本就直接失败，仅 DEBUG 演示可用，
    迁移后 DEBUG 演示图需改用 tool_executor + 真实/mock tool_code）。
    原地修改并返回 graph_json。
    """
    nodes = (graph_json or {}).get("nodes") or []
    migrated = 0
    for node in nodes:
        if node.get("type") != LEGACY_TOOL_NODE_TYPE:
            continue
        migrated += 1
        config = node.get("config") or {}
        new_config: dict[str, Any] = {}
        if config.get("tool_name"):
            new_config["toolCode"] = config["tool_name"]
        legacy_output = config.get("outputVariable") or config.get("output_variable")
        if legacy_output:
            new_config["outputVariable"] = legacy_output
        if config.get("mock_data"):
            logger.warning(
                "节点 '%s'（原 tool）的 mock_data 配置无真实执行语义，已随下架迁移丢弃",
                node.get("name", node.get("id")),
            )
        node["config"] = new_config
        node["type"] = "tool_executor"
    if migrated:
        logger.info("存量图迁移：%d 个 deprecated tool 节点已转为 tool_executor", migrated)
    return graph_json


def graph_has_interrupt_nodes(graph_json: dict[str, Any]) -> bool:
    """判断图内是否存在依赖 checkpointer 断点续跑的中断类节点（空图/缺 nodes 字段返回 False）。"""
    return any(n.get("type") in INTERRUPT_NODE_TYPES for n in (graph_json or {}).get("nodes", []))


def _conditional_has_route(node: dict[str, Any], edges: list) -> bool:
    """条件节点是否至少解析出一条非 END 路由（三期B6 / WF-P2-5）。

    两条判定线（任一满足即可）：
    - 带 sourceHandle 的路由出边（true/false、case_*、intent_*、default）——正常图
      的路由来源，编译期据此推导 target_route 并注册条件边；
    - config 显式路由（condition 的 trueRoute/falseRoute、switch/intent 的
      defaultRoute）——历史图/手工构造图的兜底，有 default 兜底即不会静默终结。
    """
    ntype = node.get("type")
    config = node.get("config") or {}
    if ntype == "condition" and (config.get("trueRoute") or config.get("falseRoute")):
        return True
    if ntype in ("switch", "intent_classifier") and config.get("defaultRoute"):
        return True
    for e in edges:
        if e.get("source") != node.get("id"):
            continue
        handle = str(e.get("sourceHandle") or "")
        if ntype == "condition" and handle in ("true", "false"):
            return True
        if handle == "default" or handle.startswith(("case_", "intent_")):
            return True
    return False


def validate_graph(graph_json: dict[str, Any]) -> None:
    """
    工作流图拓扑结构校验，验证完整性与防错
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    # 显式校验每个节点 id/type 必填，给出友好错误而非静默跳过或裸 KeyError
    for idx, n in enumerate(nodes):
        if not n.get("id"):
            raise ValueError(f"第 {idx + 1} 个节点缺少 id 字段。")
        if not n.get("type"):
            raise ValueError(f"节点 '{n['id']}' 缺少 type 字段。")
        if n.get("type") == LEGACY_TOOL_NODE_TYPE:
            # 正常加载路径已在入口 migrate_legacy_tool_nodes 自动迁移，此处拦截
            # 绕过加载入口直造 graph_json 的调用（防旧类型混入编译）
            raise ValueError(
                f"节点 '{n.get('name', n['id'])}' 使用了已下架的 'tool' 节点类型，"
                "请改用工具执行器（tool_executor）节点。"
            )

    nodes_map = {n["id"]: n for n in nodes if "id" in n}

    node_ids = {n["id"] for n in nodes if "id" in n}
    node_types = {n["id"]: n.get("type") for n in nodes if "id" in n}

    # 1. 缺少 START 节点校验
    start_nodes = [nid for nid, t in node_types.items() if t == "start"]
    if len(start_nodes) == 0:
        raise ValueError("工作流定义必须包含一个 'start' (开始) 节点。")
    if len(start_nodes) > 1:
        raise ValueError("工作流定义不能包含多个 'start' (开始) 节点。")
    # 1.1 start 节点必须有出边：否则图无入口，langgraph 编译会报 "Graph must have an entrypoint"
    if not any(edge.get("source") == start_nodes[0] for edge in edges):
        raise ValueError("'start' (开始) 节点必须连接到至少一个下游节点。")

    # 2. 悬空边与重复边校验
    seen_edges = set()
    for i, edge in enumerate(edges):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            raise ValueError(f"第 {i + 1} 条连线缺少 source 或 target 属性。")
        if source not in node_ids:
            raise ValueError(f"连线引用的源节点 ID '{source}' 在节点列表中不存在。")
        if target not in node_ids:
            raise ValueError(f"连线引用的目标节点 ID '{target}' 在节点列表中不存在。")

        edge_key = (source, target)
        if edge_key in seen_edges:
            raise ValueError(f"连线重复：从 '{source}' 到 '{target}' 的连线被定义了多次。")
        seen_edges.add(edge_key)

    # 3. 子图节点体路由校验
    for n in nodes:
        ntype = n.get("type")
        if ntype in SUBGRAPH_NODE_TYPES:
            config = convert_keys_to_snake(n.get("config", {}))
            node_name = n.get("name", n["id"])

            # 优先尝试 parentNode（group 容器）模式
            parent_result = _find_body_nodes_by_parent(nodes, edges, n["id"])
            if parent_result[0]:
                body_node_ids = parent_result[0]
            else:
                # 回退到 BFS 模式（旧工作流）
                body_route = config.get("loop_body_route")
                if not body_route:
                    raise ValueError(f"节点 '{node_name}' 未配置循环体入口节点。")
                if body_route not in node_ids:
                    raise ValueError(f"节点 '{node_name}' 的循环体入口 '{body_route}' 不存在。")
                body_node_ids = _find_body_nodes(n["id"], body_route, edges)

            # 体节点不得包含中断类节点（WF-P1-4）：体子图独立编译、不挂 checkpointer，
            # 中断（human_input）在其中触发后无法恢复（主图 checkpointer 救不了子图）。
            interrupt_hits = {nid for nid in body_node_ids if node_types.get(nid) in INTERRUPT_NODE_TYPES}
            if interrupt_hits:
                hit_names = "、".join((nodes_map[nid].get("name") or nid) for nid in interrupt_hits if nid in nodes_map)
                raise ValueError(
                    f"节点 '{node_name}' 的循环/批处理体内不能包含人工输入等中断类节点（{hit_names}）："
                    "体子图独立执行、无断点挂载，运行到中断将无法恢复。"
                    "请将该节点移出循环体，或把人工确认环节放到循环结束后。"
                )

            # 从画布边推导退出路径：穿透 group 容器
            exit_targets = []
            for edge in edges:
                if edge["source"] != n["id"]:
                    continue
                tgt = edge["target"]
                if tgt in body_node_ids or tgt == n["id"]:
                    continue
                tgt_type = node_types.get(tgt)
                if tgt_type == "loop_body_group":
                    # 穿透 group：查找 group → X 的出边作为实际退出目标
                    for g_edge in edges:
                        if g_edge["source"] == tgt:
                            g_tgt = g_edge["target"]
                            if g_tgt not in body_node_ids and g_tgt != n["id"]:
                                exit_targets.append(g_tgt)
                else:
                    exit_targets.append(tgt)
            if not exit_targets:
                raise ValueError(
                    f"节点 '{node_name}' 没有指向循环体外部的连线。请为循环控制节点添加一条连向后续节点的出边。"
                )

            # 检查体入口歧义
            if body_node_ids:
                entries = [
                    nid
                    for nid in body_node_ids
                    if not any(e["target"] == nid and e["source"] in body_node_ids for e in edges)
                ]
                if len(entries) > 1:
                    names = [nodes_map[eid].get("label", eid) for eid in entries if eid in nodes_map]
                    raise ValueError(f"循环体有多个可能的入口节点: {', '.join(names)}。请用连线明确节点执行顺序。")
                if len(entries) == 0 and len(body_node_ids) > 0:
                    raise ValueError("循环体内部存在环路，无法确定入口节点。")

    # 4. 孤立节点校验（子图体节点豁免：它们通过回边连向父节点，不在主图直接连通）
    # 先收集所有子图节点的体节点 ID，这些节点不需要在主图中表现为"已连通"
    all_body_node_ids = set()
    for n in nodes:
        ntype = n.get("type")
        if ntype in SUBGRAPH_NODE_TYPES:
            parent_result = _find_body_nodes_by_parent(nodes, edges, n["id"])
            if parent_result[0]:
                all_body_node_ids.update(parent_result[0])
            else:
                config = convert_keys_to_snake(n.get("config", {}))
                body_entry = config.get("loop_body_route")
                if body_entry and body_entry in node_ids:
                    all_body_node_ids.update(_find_body_nodes(n["id"], body_entry, edges))

    _iso_group_to_controller = _build_group_to_controller_map(nodes, edges, nodes_map)

    connected_nodes = set()
    for edge in edges:
        s, t = edge["source"], edge["target"]
        s_type = node_types.get(s)
        # source 是 group 时替换为对应 controller
        if s_type == "loop_body_group":
            s = _iso_group_to_controller.get(s, s)
        # target 是 group 时不计入连通性（group 是纯视觉节点）
        if node_types.get(t) == "loop_body_group":
            connected_nodes.add(s)
            continue
        connected_nodes.add(s)
        connected_nodes.add(t)

    for nid, ntype in node_types.items():
        if (
            ntype not in ("start", "end", "loop_body_group")
            and nid not in connected_nodes
            and nid not in all_body_node_ids
        ):
            node_name = nid
            for n in nodes:
                if n.get("id") == nid:
                    node_name = n.get("name", nid)
                    break
            raise ValueError(f"检测到孤立的工作节点 '{node_name}' (ID: {nid})，必须为它建立输入和输出连线。")

    # 5. 无条件静态环路检测 (DFS 环检测)
    # 仅针对非条件节点的静态连线建图（条件节点能基于运行时决策打破环路）
    _v_group_to_controller = _build_group_to_controller_map(nodes, edges, nodes_map)

    adj = {nid: [] for nid in node_ids}

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        source_type = node_types.get(source)

        # 穿透 group：source 是 group 时替换为对应 controller
        if source_type == "loop_body_group":
            source = _v_group_to_controller.get(source)
            if not source:
                continue
            source_type = node_types.get(source)
        # target 是 group 的边不参与主图环检测
        if node_types.get(target) == "loop_body_group":
            continue

        if source_type not in CONDITIONAL_NODE_TYPES:
            adj[source].append(target)

    # DFS 状态跟踪：0 = 未访问, 1 = 正在访问, 2 = 已完全访问
    visit_state = {nid: 0 for nid in node_ids}

    def dfs_has_cycle(u: str) -> bool:
        visit_state[u] = 1  # 正在访问
        for v in adj[u]:
            if visit_state[v] == 1:
                return True
            if visit_state[v] == 0:
                if dfs_has_cycle(v):
                    return True
        visit_state[u] = 2  # 已完全访问
        return False

    for nid in node_ids:
        if visit_state[nid] == 0:
            if dfs_has_cycle(nid):
                node_name = nid
                for n in nodes:
                    if n.get("id") == nid:
                        node_name = n.get("name", nid)
                        break
                raise ValueError(
                    f"检测到无条件死循环：静态流程在节点 '{node_name}' (ID: {nid}) 附近形成了闭环且没有任何判定条件分支。"
                )

    # 6. 模型节点配置完整性校验
    model_required_types = {"llm", "intent_classifier", "image_generator"}
    for n in nodes:
        ntype = n.get("type")
        if ntype in model_required_types:
            config = n.get("config", {})
            if not config:
                node_name = n.get("name", n["id"])
                raise ValueError(f"节点 '{node_name}' 缺少配置信息。")
            if ntype == "intent_classifier":
                # 三期B6：空 intents 的意图节点不经过 LLM（执行器直落 default_route），
                # 不再强制 model；空 intents 本身由下方第 7 步的路由校验兜底提示
                if not (config.get("intents") or []):
                    continue
            profile_code = config.get("modelProfileCode", "")
            if not profile_code or not profile_code.strip():
                node_name = n.get("name", n["id"])
                raise ValueError(f"节点 '{node_name}' 未选择模型 Profile，请先在配置面板中选择一个模型。")

    # 7. 条件类节点至少一条非 END 路由（三期B6 / WF-P2-5 + WF-P2-12）
    # 路由边 = 带 sourceHandle（true/false、case_*、intent_*、default）的出边，编译期
    # 由此推导 target_route 并注册条件边；config 显式路由（trueRoute/defaultRoute 等，
    # 历史图/手工图）同样有效。两者皆无 → 编译后该节点无出边、执行静默终结——拒绝。
    for n in nodes:
        ntype = n.get("type")
        if ntype not in CONDITIONAL_NODE_TYPES:
            continue
        if _conditional_has_route(n, edges):
            continue
        node_name = n.get("name", n["id"])
        raise ValueError(
            f"条件分支节点 '{node_name}'（{ntype}）没有任何可解析的路由：缺少带分支句柄的连线"
            "（true/false、case、intent、default），编译后执行到该节点会静默终结。"
            "请为它的各分支连接下游节点，或删除该节点。"
        )

    # 8. 节点 config schema 校验（三期B6 / WF-P2-5）：必填字段与类型，
    # 消除「配置不全 → 运行期静默走默认/空转」（详见 node_schema.py）。
    # 复审 P1-2：不再跳过空 config——validate_node_config 对无 schema 的类型
    # 自然放行，此前 `if not config: continue` 让 condition 无 config 但有
    # handle 边的图绕过必填校验，编译期 expression 缺失回落恒真 "True" 兜底
    # （正是 schema 要消除的静默面）
    for n in nodes:
        config = n.get("config") or {}
        validate_node_config(n.get("type", ""), config, n.get("name", n["id"]))


def _build_group_to_controller_map(nodes: list, edges: list, nodes_map: dict) -> dict[str, str]:
    group_to_controller = {}
    for node in nodes:
        if node.get("type") == "loop_body_group":
            cfg = convert_keys_to_snake(node.get("config", {}))
            ctrl = cfg.get("controller_node_id")
            if ctrl:
                group_to_controller[node["id"]] = ctrl
            else:
                for edge in edges:
                    if edge.get("target") == node["id"]:
                        src_id = edge.get("source")
                        src_node = nodes_map.get(src_id)
                        if src_node and src_node.get("type") in ["loop_controller", "batch_processor"]:
                            group_to_controller[node["id"]] = src_id
                            break
    return group_to_controller


def _find_body_nodes(parent_id: str, body_entry_id: str, edges: list) -> set[str]:
    """BFS 从 body_entry_id 出发，沿 forward edges 遍历，直到遇到 parent_id 停止。"""
    if body_entry_id == parent_id:
        raise ValueError(
            f"循环体入口节点不能指向循环控制节点自身 (ID: {parent_id})。请选择一个不同的节点作为循环体入口。"
        )
    body_nodes = set()
    queue = collections.deque([body_entry_id])
    visited = set()

    while queue:
        current = queue.popleft()
        if current in visited or current == parent_id:
            continue
        visited.add(current)
        body_nodes.add(current)

        for edge in edges:
            if edge["source"] == current:
                target = edge["target"]
                if target not in visited:
                    queue.append(target)

    return body_nodes


def _find_body_nodes_by_parent(nodes: list, edges: list, controller_id: str) -> tuple[set[str], str | None]:
    """
    通过 parentNode 字段识别体节点（前端 group 容器模式）。
    流程：controller config.bodyGroupId → 找 group 子节点 → 推导入口。
    返回 (body_node_ids, body_entry_id)，未找到时返回 (set(), None)。
    """
    ctrl_node = next((n for n in nodes if n["id"] == controller_id), None)
    if not ctrl_node:
        return set(), None
    config = convert_keys_to_snake(ctrl_node.get("config", {}))
    group_id = config.get("body_group_id")
    if not group_id:
        # 尝试从边推导：找源头为 controller，目标为 loop_body_group 节点的边
        for e in edges:
            if e["source"] == controller_id:
                tgt_node = next((n for n in nodes if n["id"] == e["target"]), None)
                if tgt_node and tgt_node.get("type") == "loop_body_group":
                    group_id = tgt_node["id"]
                    break

    if not group_id:
        return set(), None

    # 找 parentNode == group_id 的节点
    body_node_ids = {n["id"] for n in nodes if n.get("parentNode") == group_id}
    if not body_node_ids:
        return set(), None

    # 推导体入口：group 内没有来自 group 内部入边的节点
    body_entry = None
    for nid in body_node_ids:
        has_internal_incoming = any(e["target"] == nid and e["source"] in body_node_ids for e in edges)
        if not has_internal_incoming:
            body_entry = nid
            break
    if not body_entry:
        body_entry = next(iter(body_node_ids))

    return body_node_ids, body_entry
