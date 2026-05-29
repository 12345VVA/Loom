import json
import os

# Helper to generate elements
def create_node(node_id, ntype, label, x, y, config, parent_node=None, extent=None, expand_parent=False, style=None):
    node = {
        "id": node_id,
        "type": ntype,
        "position": {"x": x, "y": y},
        "data": {"config": config},
        "label": label
    }
    if parent_node:
        node["parentNode"] = parent_node
    if extent:
        node["extent"] = extent
    if expand_parent:
        node["expandParent"] = expand_parent
    if style:
        node["style"] = style
    return node

def create_edge(source, target, edge_type="default", condition="", source_handle=None):
    edge_id = f"edge_{source}_{target}"
    if source_handle:
        edge_id += f"_{source_handle}"
    
    edge = {
        "id": edge_id,
        "type": edge_type,
        "source": source,
        "target": target,
        "data": {"condition": condition},
        "label": "",
        "animated": True,
        "style": {"stroke": "#409eff", "strokeWidth": 2}
    }
    if source_handle:
        edge["sourceHandle"] = source_handle
    return edge

def build_workflow_json(name, description, elements):
    # Derive nodes and edges exactly like editor.vue
    nodes = []
    edges = []
    
    for el in elements:
        if "source" in el:
            # It's an edge
            edges.append(el)
        else:
            # It's a node
            nodes.append(el)
            
    # Serialize nodes for backend
    backend_nodes = []
    for n in nodes:
        conf = n.get("data", {}).get("config", {})
        serialized = {
            "id": n["id"],
            "type": n["type"],
            "name": n["label"],
            "config": conf
        }
        if "parentNode" in n: serialized["parentNode"] = n["parentNode"]
        if "extent" in n: serialized["extent"] = n["extent"]
        if "expandParent" in n: serialized["expandParent"] = n["expandParent"]
        if "style" in n: serialized["style"] = n["style"]
        backend_nodes.append(serialized)
        
    backend_edges = []
    for e in edges:
        edge = {
            "source": e["source"],
            "target": e["target"],
            "type": e.get("type", "direct"),
            "condition": e.get("data", {}).get("condition", "")
        }
        if "sourceHandle" in e: edge["sourceHandle"] = e["sourceHandle"]
        if e.get("data", {}).get("label"): edge["data"] = {"label": e["data"]["label"]}
        backend_edges.append(edge)
        
    graph_payload = {
        "elements": elements,
        "nodes": backend_nodes,
        "edges": backend_edges
    }
    
    export_data = {
        "version": "1.0",
        "type": "LoomWorkflow",
        "metadata": {
            "name": name,
            "description": description
        },
        "graph_json": json.dumps(graph_payload, ensure_ascii=False)
    }
    
    return export_data

def save_workflow(name, filename, description, elements):
    out_dir = os.path.join(os.path.dirname(__file__), "..", "examples", "workflows")
    os.makedirs(out_dir, exist_ok=True)
    
    export_data = build_workflow_json(name, description, elements)
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"Generated {filepath}")

def generate_01():
    elements = [
        create_node("node_start", "start", "开始", 100, 150, {"inputVariables": ["topic"]}),
        create_node("node_llm", "llm", "文案生成", 400, 150, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "请根据主题：{topic}，写一段大约100字的简介。",
            "outputFormat": "text",
            "outputVariable": "summary"
        }),
        create_node("node_end", "end", "结束", 700, 150, {
            "outputFormat": "json",
            "outputFields": [{"name": "result", "type": "string", "value": "{summary}", "children": []}]
        }),
        create_edge("node_start", "node_llm"),
        create_edge("node_llm", "node_end")
    ]
    save_workflow("01_基础文本生成测试流", "01_Basic_QA_Workflow.json", "最简单的 LLM 单节点处理范例", elements)

def generate_02():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["user_input"]}),
        create_node("node_intent", "intent_classifier", "意图识别", 350, 200, {
            "modelProfileCode": "deepseek-default",
            "intents": [
                {"name": "闲聊", "description": "日常打招呼、闲聊", "value": "chat", "targetRoute": "node_chat"},
                {"name": "查询天气", "description": "询问天气状况", "value": "weather", "targetRoute": "node_weather"}
            ],
            "inputVariable": "{user_input}",
            "outputVariable": "intent_result"
        }),
        create_node("node_chat", "llm", "闲聊回复", 650, 100, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "用户：{user_input}\\n你是一个幽默的朋友，请回复。",
            "outputFormat": "text",
            "outputVariable": "chat_reply"
        }),
        create_node("node_weather", "tool_executor", "天气查询(Mock)", 650, 300, {
            "toolCode": "mock_weather_api",
            "argumentsJson": '{"location": "北京"}',
            "outputVariable": "weather_info"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "outputFormat": "json",
            "outputFields": [
                {"name": "reply", "type": "string", "value": "{chat_reply}{weather_info}", "children": []}
            ]
        }),
        create_edge("node_start", "node_intent"),
        create_edge("node_intent", "node_chat", source_handle="intent_0"),
        create_edge("node_intent", "node_weather", source_handle="intent_1"),
        create_edge("node_chat", "node_end"),
        create_edge("node_weather", "node_end")
    ]
    save_workflow("02_意图识别分流", "02_Intent_Routing_Workflow.json", "演示使用大模型做意图分类，并走向不同下游分支", elements)

def generate_03():
    elements = [
        create_node("node_start", "start", "开始", 100, 150, {"inputVariables": ["search_query"]}),
        create_node("node_search", "tool_executor", "联网搜索", 350, 150, {
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{search_query}"}',
            "outputVariable": "search_results"
        }),
        create_node("node_llm", "llm", "整理答案", 650, 150, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "问题：{search_query}\\n\\n搜索结果：{search_results}\\n\\n请根据搜索结果总结最终答案。",
            "outputFormat": "text",
            "outputVariable": "final_answer"
        }),
        create_node("node_end", "end", "结束", 950, 150, {
            "outputFormat": "json",
            "outputFields": [{"name": "answer", "type": "string", "value": "{final_answer}", "children": []}]
        }),
        create_edge("node_start", "node_search"),
        create_edge("node_search", "node_llm"),
        create_edge("node_llm", "node_end")
    ]
    save_workflow("03_智能体工具协同流", "03_Agent_Tool_Workflow.json", "演示如何调用外部工具（如联网搜索）并将结果交由 LLM 处理", elements)

def generate_04():
    elements = [
        create_node("node_start", "start", "开始", 100, 300, {"inputVariables": ["json_list"]}),
        create_node("node_loop_ctrl", "loop_controller", "循环控制器", 350, 300, {
            "arrayVariable": "{json_list}",
            "itemVariable": "item",
            "concurrency": 2
        }),
        create_node("loop_body_group", "loop_body_group", "循环体容器", 350, 400, {}, style={"width": "300px", "height": "200px"}),
        create_node("node_loop_llm", "llm", "处理每一项", 50, 50, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "处理数据项：{item}\\n请翻译为英文。",
            "outputFormat": "text",
            "outputVariable": "translated_item"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 800, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "done", "type": "string", "value": "true", "children": []}]
        }),
        create_edge("node_start", "node_loop_ctrl"),
        # Entrance to loop body group (implicit logic handles internals)
        create_edge("node_loop_ctrl", "loop_body_group"),
        # Exit from loop body group back to main flow
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("04_并发循环批处理流", "04_Loop_Processing_Workflow.json", "演示如何使用循环控制器处理数组，并发调用内部节点", elements)

def generate_05():
    elements = [
        create_node("node_start", "start", "开始", -200, 300, {"inputVariables": ["theme"]}),
        
        create_node("node_human", "human_input", "人工确认主题", 100, 300, {
            "approvalMessage": "是否允许开始创作关于：{theme} 的内容？"
        }),
        
        create_node("node_switch", "switch", "路由分发", 400, 300, {
            "variable": "difficulty",
            "cases": [
                {"value": "easy", "targetRoute": "node_llm_easy"},
                {"value": "hard", "targetRoute": "node_llm_hard"}
            ]
        }),
        
        create_node("node_llm_easy", "llm", "生成简单文本", 700, 150, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n写个简单的故事。",
            "outputFormat": "text",
            "outputVariable": "story_text"
        }),
        
        create_node("node_llm_hard", "llm", "生成复杂结构", 1000, 450, {
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n生成一个详细的结构 JSON，包含 scenes 数组。",
            "outputFormat": "text",
            "outputVariable": "complex_structure"
        }),
        
        create_node("node_image", "image_generator", "生图节点", 1000, 150, {
            "modelProfileCode": "dall-e-3",
            "promptTemplate": "为这个故事配图：{story_text}",
            "outputVariable": "image_url"
        }),
        
        create_node("node_end", "end", "结束", 1300, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "finished", "type": "string", "value": "true", "children": []}]
        }),
        
        create_edge("node_start", "node_human"),
        create_edge("node_human", "node_switch"),
        create_edge("node_switch", "node_llm_easy", source_handle="case_0"),
        create_edge("node_switch", "node_llm_hard", source_handle="case_1"),
        create_edge("node_llm_easy", "node_image"),
        create_edge("node_image", "node_end"),
        create_edge("node_llm_hard", "node_end")
    ]
    save_workflow("05_终极大乱斗综合测试", "05_Comprehensive_Test_Workflow.json", "涵盖人工审批、生图、条件路由等高级节点的全链路压测模板", elements)

def generate_06():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["score"]}),
        create_node("node_condition", "condition", "分数判断", 350, 200, {
            "expression": "score >= 60",
            "trueRoute": "node_tool_pass",
            "falseRoute": "node_tool_fail"
        }),
        create_node("node_tool_pass", "tool", "记录及格", 650, 100, {
            "outputVariable": "record_result",
            "mockData": "已记录为及格"
        }),
        create_node("node_tool_fail", "tool", "记录不及格", 650, 300, {
            "outputVariable": "record_result",
            "mockData": "已记录为不及格，需要补考"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "outputFormat": "json",
            "outputFields": [{"name": "result", "type": "string", "value": "{record_result}", "children": []}]
        }),
        create_edge("node_start", "node_condition"),
        create_edge("node_condition", "node_tool_pass", source_handle="true"),
        create_edge("node_condition", "node_tool_fail", source_handle="false"),
        create_edge("node_tool_pass", "node_end"),
        create_edge("node_tool_fail", "node_end")
    ]
    save_workflow("06_二元条件与Mock工具", "06_Condition_Branch_Workflow.json", "演示基础的二元条件分支(Condition)节点和Mock工具节点的作用", elements)

def generate_07():
    elements = [
        create_node("node_start", "start", "开始", 100, 300, {"inputVariables": ["url_list"]}),
        create_node("node_batch", "batch_processor", "并发批处理器", 350, 300, {
            "arrayVariable": "{url_list}",
            "itemVariable": "url",
            "concurrency": 5
        }),
        create_node("loop_body_group", "loop_body_group", "批处理内部容器", 350, 400, {}, style={"width": "300px", "height": "200px"}),
        create_node("node_scrape", "tool_executor", "抓取网页", 50, 50, {
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{{ variables.url }}"}',
            "outputVariable": "page_content"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 800, 300, {
            "outputFormat": "json",
            "outputFields": [{"name": "status", "type": "string", "value": "finished", "children": []}]
        }),
        create_edge("node_start", "node_batch"),
        create_edge("node_batch", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("07_并发批处理流", "07_Batch_Processing_Workflow.json", "演示批处理节点的高并发抓取或处理能力", elements)

if __name__ == "__main__":
    generate_01()
    generate_02()
    generate_03()
    generate_04()
    generate_05()
    generate_06()
    generate_07()
