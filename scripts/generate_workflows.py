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
        # 拷贝一份 config，避免污染 elements 里保留的画布态原始字段
        conf = {**n.get("data", {}).get("config", {})}
        # 与 editor 导出(useGraphBuilder)保持一致：
        # tool_executor 的 argumentsJson(字符串) → arguments(对象)，nodes 层只保留 arguments
        if n["type"] == "tool_executor" and "argumentsJson" in conf:
            try:
                conf["arguments"] = json.loads(conf["argumentsJson"] or "{}")
            except json.JSONDecodeError:
                conf["arguments"] = {}
            del conf["argumentsJson"]
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
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
            "modelProfileCode": "deepseek-default",
            "intents": [
                {"id": "chat", "name": "闲聊", "description": "日常打招呼、闲聊", "value": "chat", "targetRoute": "node_chat"},
                {"id": "weather", "name": "查询天气", "description": "询问天气状况", "value": "weather", "targetRoute": "node_weather"}
            ],
            "inputVariable": "{user_input}",
            "outputVariable": "intent_result"
        }),
        create_node("node_chat", "llm", "闲聊回复", 650, 100, {
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
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
            "inputs": [
                {"name": "chat_reply", "type": "string", "source": ["node_chat", "chat_reply"]},
                {"name": "weather_info", "type": "string", "source": ["node_weather", "weather_info"]}
            ],
            "outputFormat": "json",
            "outputFields": [
                {"name": "reply", "type": "string", "value": "{chat_reply}{weather_info}", "children": []}
            ]
        }),
        create_edge("node_start", "node_intent"),
        create_edge("node_intent", "node_chat", source_handle="intent_chat"),
        create_edge("node_intent", "node_weather", source_handle="intent_weather"),
        create_edge("node_chat", "node_end"),
        create_edge("node_weather", "node_end")
    ]
    save_workflow("02_意图识别分流", "02_Intent_Routing_Workflow.json", "演示使用大模型做意图分类，并走向不同下游分支", elements)

def generate_03():
    elements = [
        create_node("node_start", "start", "开始", 100, 150, {"inputVariables": ["search_query"]}),
        create_node("node_search", "tool_executor", "联网搜索", 350, 150, {
            "inputs": [{"name": "search_query", "type": "string", "source": ["node_start", "search_query"]}],
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{search_query}"}',
            "outputVariable": "search_results"
        }),
        create_node("node_llm", "llm", "整理答案", 650, 150, {
            "inputs": [
                {"name": "search_query", "type": "string", "source": ["node_start", "search_query"]},
                {"name": "search_results", "type": "string", "source": ["node_search", "search_results"]}
            ],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "问题：{search_query}\\n\\n搜索结果：{search_results}\\n\\n请根据搜索结果总结最终答案。",
            "outputFormat": "text",
            "outputVariable": "final_answer"
        }),
        create_node("node_end", "end", "结束", 950, 150, {
            "inputs": [{"name": "final_answer", "type": "string", "source": ["node_llm", "final_answer"]}],
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
            "inputs": [{"name": "json_list", "type": "string", "source": ["node_start", "json_list"]}],
            "arrayVariable": "{json_list}",
            "itemVariable": "item",
            "concurrency": 2
        }),
        create_node("loop_body_group", "loop_body_group", "循环体容器", 350, 400, {"controllerNodeId": "node_loop_ctrl"}, style={"width": "300px", "height": "200px"}),
        create_node("node_loop_llm", "llm", "处理每一项", 50, 50, {
            "inputs": [{"name": "item", "type": "string", "source": ["node_loop_ctrl", "item"]}],
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
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "message": "是否允许开始创作关于：{theme} 的内容？"
        }),
        
        create_node("node_switch", "switch", "路由分发", 400, 300, {
            "variable": "difficulty",
            "cases": [
                {"id": "easy", "value": "easy", "targetRoute": "node_llm_easy"},
                {"id": "hard", "value": "hard", "targetRoute": "node_llm_hard"}
            ]
        }),
        
        create_node("node_llm_easy", "llm", "生成简单文本", 700, 150, {
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n写个简单的故事。",
            "outputFormat": "text",
            "outputVariable": "story_text"
        }),
        
        create_node("node_llm_hard", "llm", "生成复杂结构", 1000, 450, {
            "inputs": [{"name": "theme", "type": "string", "source": ["node_start", "theme"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": "主题：{theme}\\n生成一个详细的结构 JSON，包含 scenes 数组。",
            "outputFormat": "text",
            "outputVariable": "complex_structure"
        }),
        
        create_node("node_image", "image_generator", "生图节点", 1000, 150, {
            "inputs": [{"name": "story_text", "type": "string", "source": ["node_llm_easy", "story_text"]}],
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
        create_edge("node_switch", "node_llm_easy", source_handle="case_easy"),
        create_edge("node_switch", "node_llm_hard", source_handle="case_hard"),
        create_edge("node_llm_easy", "node_image"),
        create_edge("node_image", "node_end"),
        create_edge("node_llm_hard", "node_end")
    ]
    save_workflow("05_终极大乱斗综合测试", "05_Comprehensive_Test_Workflow.json", "涵盖人工审批、生图、条件路由等高级节点的全链路压测模板", elements)

def generate_06():
    # 本示例演示「二元条件分支 + Mock 固定文案返回」。tool 节点在前端虽标记为
    # deprecated（新建菜单已禁用），但其 mock_data 语义（直接返回固定文本）在
    # tool_executor 中无法表达（tool_executor 按 toolCode 分发到具体工具）。
    # 故此处保留 tool 节点用于 mock 占位；正式工具调用请使用 tool_executor 节点。
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["score"]}),
        create_node("node_condition", "condition", "分数判断", 350, 200, {
            "inputs": [{"name": "score", "type": "number", "source": ["node_start", "score"]}],
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
            "inputs": [{"name": "record_result", "type": "string", "source": ["node_tool_pass", "record_result"]}],
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
            "inputs": [{"name": "url_list", "type": "string", "source": ["node_start", "url_list"]}],
            "arrayVariable": "{url_list}",
            "itemVariable": "url",
            "concurrency": 5
        }),
        create_node("loop_body_group", "loop_body_group", "批处理内部容器", 350, 400, {"controllerNodeId": "node_batch"}, style={"width": "300px", "height": "200px"}),
        create_node("node_scrape", "tool_executor", "抓取网页", 50, 50, {
            "inputs": [{"name": "url", "type": "string", "source": ["node_batch", "url"]}],
            "toolCode": "serp_api_search",
            "argumentsJson": '{"query": "{url}"}',
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

def generate_08():
    elements = [
        create_node("node_start", "start", "开始", 100, 200, {"inputVariables": ["user_json"]}),
        create_node("node_assign", "variable_assignment", "变量赋值", 350, 200, {
            "assignments": [
                {"variable_name": "temp_value", "value_type": "string", "value": "Initial Value"},
                {"variable_name": "computed_value", "value_type": "expression", "value": "1 + 1"}
            ]
        }),
        create_node("node_transform", "variable_transform", "变量转换", 650, 200, {
            "inputs": [{"name": "user_json", "type": "string", "source": ["node_start", "user_json"]}],
            "input_variable": "{user_json}",
            "transform_type": "extract_json_path",
            "transform_args": {"path": "data.items.0"},
            "output_variable": "extracted_item"
        }),
        create_node("node_end", "end", "结束", 950, 200, {
            "inputs": [
                {"name": "temp_value", "type": "string", "source": ["node_assign", "temp_value"]},
                {"name": "computed_value", "type": "string", "source": ["node_assign", "computed_value"]},
                {"name": "extracted_item", "type": "string", "source": ["node_transform", "extracted_item"]}
            ],
            "outputFormat": "json",
            "outputFields": [
                {"name": "temp", "type": "string", "value": "{temp_value}", "children": []},
                {"name": "computed", "type": "string", "value": "{computed_value}", "children": []},
                {"name": "extracted", "type": "string", "value": "{extracted_item}", "children": []}
            ]
        }),
        create_edge("node_start", "node_assign"),
        create_edge("node_assign", "node_transform"),
        create_edge("node_transform", "node_end")
    ]
    save_workflow("08_变量操作测试流", "08_Variable_Operations_Workflow.json", "专门测试变量赋值与格式转换节点", elements)

def generate_09():
    elements = [
        create_node("node_start", "start", "开始", 100, 400, {"inputVariables": ["user_input"]}),
        create_node("node_assign", "variable_assignment", "初始化变量", 350, 400, {
            "assignments": [{"variable_name": "status", "value_type": "string", "value": "pending"}]
        }),
        create_node("node_intent", "intent_classifier", "意图识别", 600, 400, {
            "inputs": [{"name": "user_input", "type": "string", "source": ["node_start", "user_input"]}],
            "modelProfileCode": "deepseek-default",
            "intents": [
                {"id": "weather", "name": "询问天气", "value": "weather", "targetRoute": "node_tool_weather"},
                {"id": "task", "name": "复杂任务", "value": "task", "targetRoute": "node_human"}
            ],
            "inputVariable": "{user_input}",
            "outputVariable": "intent"
        }),
        create_node("node_tool_weather", "tool_executor", "天气查询", 900, 200, {
            "toolCode": "mock_weather_api",
            "argumentsJson": '{"location": "北京"}',
            "outputVariable": "weather_res"
        }),
        create_node("node_human", "human_input", "人工审批", 900, 600, {
            "message": "是否允许执行复杂任务？",
            "outputVariable": "approval_res"
        }),
        create_node("node_cond", "condition", "审批判断", 1200, 600, {
            "expression": "approval_res == True",
            "trueRoute": "node_batch",
            "falseRoute": "node_end"
        }),
        create_node("node_batch", "batch_processor", "批量处理", 1500, 500, {
            "arrayVariable": "['task1', 'task2', 'task3']",
            "itemVariable": "task",
            "concurrency": 3
        }),
        create_node("loop_body_group", "loop_body_group", "处理组", 1500, 600, {"controllerNodeId": "node_batch"}, style={"width": "300px", "height": "200px"}),
        create_node("node_loop_tool", "tool_executor", "执行任务", 50, 50, {
            "inputs": [{"name": "task", "type": "string", "source": ["node_batch", "task"]}],
            "toolCode": "mock_tool",
            "argumentsJson": '{"task": "{task}"}',
            "outputVariable": "task_res"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 1900, 400, {
            "outputFormat": "json",
            "outputFields": [{"name": "done", "type": "string", "value": "true", "children": []}]
        }),
        create_edge("node_start", "node_assign"),
        create_edge("node_assign", "node_intent"),
        create_edge("node_intent", "node_tool_weather", source_handle="intent_weather"),
        create_edge("node_intent", "node_human", source_handle="intent_task"),
        create_edge("node_intent", "node_end", source_handle="default"),
        create_edge("node_tool_weather", "node_end"),
        create_edge("node_human", "node_cond"),
        create_edge("node_cond", "node_batch", source_handle="true"),
        create_edge("node_cond", "node_end", source_handle="false"),
        create_edge("node_batch", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("09_超级综合测试流", "09_Super_Comprehensive_Workflow.json", "涵盖大部分节点类型的超长链路复合测试流", elements)

def generate_10():
    prompt_template = """用户输入：{input_query}；
"Role": "你是一名顶尖的“小红书风格数字内容策展人”兼“家庭教育洞察专家”，同时也是一名“系列绘本视觉系统设计师”。你擅长构建统一视觉语言体系，使整组图片看起来像同一位插画师创作，具有高度一致的角色、配色、构图与材质风格。",
  "Task": "用户仅提供一个topic。你需完成故事创作，并生成一整套风格高度统一的非写实绘本图像提示词，每一张图必须属于同一视觉体系。",
  "Steps": [
    "1. 风格锁定：仅选择一种非写实艺术风格，并生成唯一Style Anchor（风格锚点），该锚点必须在所有image_prompt中原样复用（不可变化）。风格需包含：画材质感（如水彩纸颗粒）、笔触特征、配色体系（如莫兰迪）、整体氛围。",
    "2. 角色系统构建：为家长与孩子设计“唯一视觉ID”，包括：脸型（如圆脸）、发型、服装（颜色+款式）、配饰。所有image_prompt必须包含“same character design, consistent appearance”。禁止角色变化。",
    "3. 构图体系定义：统一构图规则（如：主体居中、留白充足、固定视角、相似景别）。所有图片必须使用同一构图逻辑。",
    "4. 色彩系统定义：统一使用固定色板（如：低饱和莫兰迪：米色、灰蓝、浅黄）。禁止高饱和颜色波动。",
    "5. 故事创作：创作1个5-10段的故事，每段包含一个能引发家长共鸣的教育观点，并提炼为图片嵌入文字。",
    "6. 视觉生成：为每段生成image_prompt，必须严格遵守统一结构，并在每一条中重复：Style Anchor + 角色ID + 构图规则 + 色彩规则 + 设计系统。",
    "7. 文字与设计统一：所有图片的文字排版（位置、字体、大小）和装饰元素（边框、图标）必须完全一致，仅内容变化。"
  ],
  "Constraints": [
    "必须保持非写实风格（禁止摄影感）",
    "所有image_prompt必须风格一致，不允许出现不同画风或材质",
    "必须包含嵌入式文字（中文），且描述清晰排版规则",
    "禁止出现nsfw,nude等敏感词",
    "故事数量固定为1，story_id为1",
    "输出格式必须严格一致，不得增加或删除字段"
  ],
  "Prompt_engineering_requirements": {
    "structure": "[Style Anchor: 固定风格锚点（全文复用）] + [Subject: 固定角色ID + same character design] + [Scene: 场景描述] + [Action: 动作] + [Emotion: 情绪] + [Composition: 固定构图规则] + [Color Palette: 固定色板] + [Text Overlay: 中文文字 + 固定排版规则] + [Embedded Graphics: 固定装饰系统] + [Overall Style: 唯一风格名称] + [Light/Color: 柔和光影] + [Technical Suffix: consistent style, no variation, no photorealism]",
    "technical_suffix": "consistent character design, same style, same color palette, same composition, no variation, no photorealism, soft watercolor texture"
  },
  "Output_format": {
    "topic": "string",
    "story_style": "string",
    "overall_mood": "string",
    "stories": [
      {
        "story_id": 1,
        "title": "string",
        "paragraphs": [
          {
            "paragraph_id": 1,
            "story_text": "string",
            "image_prompt": "string",
            "visual_keywords": ["string"]
          }
        ]
      }
    ]
  }"""

    json_fields = [
        {
            "name": "output",
            "type": "object",
            "children": [
                {"name": "topic", "type": "string", "description": "", "children": []},
                {"name": "story_style", "type": "string", "description": "", "children": []},
                {"name": "overall_mood", "type": "string", "description": "", "children": []},
                {
                    "name": "stories", "type": "array_object", "description": "", "children": [
                        {"name": "story_id", "type": "number", "description": "", "children": []},
                        {"name": "title", "type": "string", "description": "", "children": []},
                        {
                            "name": "paragraphs", "type": "array_object", "description": "", "children": [
                                {"name": "paragraph_id", "type": "number", "description": "", "children": []},
                                {"name": "story_text", "type": "string", "description": "", "children": []},
                                {"name": "image_prompt", "type": "string", "description": "", "children": []},
                                {"name": "visual_keywords", "type": "string", "description": "", "children": []}
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    elements = [
        create_node("node_start", "start", "开始", 50, 250, {"inputVariables": ["input_query"]}),
        create_node("node_llm", "llm", "生成绘本大纲", 300, 250, {
            "inputs": [{"name": "input_query", "type": "string", "source": ["node_start", "input_query"]}],
            "modelProfileCode": "deepseek-default",
            "promptTemplate": prompt_template,
            "outputFormat": "json",
            "jsonFields": json_fields,
            "outputVariable": "LLM_output"
        }),
        create_node("node_transform", "variable_transform", "提取段落数组", 600, 250, {
            "inputs": [{"name": "LLM_output", "type": "string", "source": ["node_llm", "LLM_output"]}],
            "input_variable": "{LLM_output}",
            "transform_type": "extract_json_path",
            "transform_args": {"path": "output.stories.0.paragraphs"},
            "output_variable": "paragraphs_array"
        }),
        create_node("node_loop", "loop_controller", "循环生成插图", 900, 250, {
            "inputs": [{"name": "paragraphs_array", "type": "string", "source": ["node_transform", "paragraphs_array"]}],
            "arrayVariable": "{paragraphs_array}",
            "itemVariable": "paragraph",
            "concurrency": 2
        }),
        create_node("loop_body_group", "loop_body_group", "插图生成容器", 900, 400, {"controllerNodeId": "node_loop"}, style={"width": "350px", "height": "200px"}),
        create_node("node_image", "image_generator", "生图节点", 50, 50, {
            "inputs": [{"name": "paragraph", "type": "string", "source": ["node_loop", "paragraph"]}],
            "modelProfileCode": "dall-e-3",
            "promptTemplate": "{paragraph.image_prompt}",
            "outputVariable": "image_url"
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 1400, 250, {
            "outputFormat": "json",
            "outputFields": [{"name": "final_result", "type": "string", "value": "绘本生成完毕", "children": []}]
        }),
        create_edge("node_start", "node_llm"),
        create_edge("node_llm", "node_transform"),
        create_edge("node_transform", "node_loop"),
        create_edge("node_loop", "loop_body_group"),
        create_edge("loop_body_group", "node_end")
    ]
    save_workflow("10_故事绘本生成流", "10_Story_Illustration_Workflow.json", "完整的故事-插图生成工作流，演示复杂的LLM JSON输出提取与循环生图", elements)

def generate_11():
    """小红书绘本内容流水线：输入话题/一段话 → 选题策划 → 故事+内页提示词 → 正文文案 → 封面+内页配图。

    方法论来源：晓悠绘本馆 23 篇全量风格分析报告（选题五层漏斗、Gen3 干货文案模板、
    封面骨架、平涂蜡笔+纸纹米白底视觉锚点）+ 阿苏角色宇宙 + Q1-Q10 质控红线。
    注意：提示词中的模板占位符后禁止紧跟英文冒号/逗号/右花括号（render_template 的排除规则）。
    """

    # 视觉锚点：报告色彩定量结论（暖色主导 85%、亮度 67%、饱和度 28.6%、蜜黄/奶油底）
    # 注：生图模型 doubao-seedream-4-5 中文文字渲染可靠，走「图文式」（文字压图），
    # 与晓悠绘本馆实际形态对齐（封面描边标题 + 内页手写体故事文字压图）。
    # v4：实测 seedream-4-5 默认审美会把画面拉向日漫数字插画（光滑喷枪渐变+动漫大眼），
    # 弱质感词压不住，必须正面强调手绘蜡笔笔触 + 明确反日漫/反光面负面词（该模型无 negative_prompt 参数）。
    STYLE_ANCHOR = (
        "hand-drawn children's picture book illustration in wax crayon and oil pastel, "
        "clearly visible crayon strokes and scribble texture, grainy off-white cream paper background, "
        "matte flat color fills with slightly rough uneven edges, childlike naive drawing style, "
        "low-saturation warm earthy color palette (honey yellow, cream, sage green, terracotta, muted cocoa brown), "
        "simple composition with generous negative space, one single scene per page, cozy bedtime mood. "
        "IMPORTANT: NOT anime, NOT manga, no glossy digital airbrushing, no smooth gradient shading, "
        "no sparkling highlight eyes, no 3D rendering, no vector-clean outlines, no photorealism"
    )

    # 角色设定表：跨篇锁定的角色宇宙（打同类账号「角色每篇一换」的死穴）
    CHARACTERS = (
        "- 阿苏 Asu: \"Asu, a 4-year-old Chinese boy, round face, short slightly-tousled black hair, "
        "simple small round black eyes, childlike naive facial features, wearing an orange-yellow hoodie and blue overalls, "
        "same character design, consistent appearance\"\n"
        "- 妈妈: \"a warm young Chinese mother with shoulder-length black hair, wearing a soft beige cardigan, "
        "same character design, consistent appearance\"\n"
        "- 白白（小兔）: \"a small white rabbit with pink inner ears, wearing a tiny mint-green scarf, "
        "same character design, consistent appearance\"\n"
        "- 憨憨（小熊）: \"a chubby brown bear with a cream-colored belly patch, "
        "same character design, consistent appearance\"\n"
        "- 啾啾（小鸟）: \"a tiny round yellow bird with a small orange beak, "
        "same character design, consistent appearance\"\n"
        "- 橙橙（小狐）: \"a small orange fox with a fluffy white-tipped tail, "
        "same character design, consistent appearance\""
    )

    PLAN_PROMPT = """用户输入（一个话题或一段话）：
{input_query}

你是小红书亲子绘本账号「阿苏的睡前故事」的选题策划。以下方法论来自对同类爆款账号 23 篇全量数据的研究，必须严格执行。

【选题漏斗】
1. 取材：只从 3-6 岁家长的日常冲突场景取材（磨蹭、没礼貌、不喝水、憋尿、不肯睡、不刷牙、怕黑、发脾气），不从童话创意取材。标题即家长的搜索词。
2. 筛选判据：这个问题能不能让角色用身体动作演出来。行为类都能演；抽象情绪类难演，除非用户输入明确指向情绪主题。
3. 题材双轨：行为管教/生理习惯类拿流量和转发（家庭群共识型题材如喝水、卫生、礼貌转发率最高）；情绪安抚类拿收藏沉淀。默认优先行为管教/生理习惯，除非输入明显是情绪主题。
4. 命名公式：书名 = 角色名 + 负面行为，痛点词直接进书名，例如《阿苏不肯睡觉》《阿苏不想刷牙》《憨憨没礼貌》。
5. 笔记标题公式：「睡前故事 | 《书名》」，书名号必带，整体不超过 20 字。

【输出要求】
- category：题材分类，三选一（行为管教 / 生理习惯 / 情绪安抚）
- book_title：绘本书名，带书名号
- note_title：小红书笔记标题，格式「睡前故事 | 《书名》」
- pain_point：一句话戳中家长痛点，用于正文开头
- core_points：3 条教育要点，每条一句话，供正文「3个方法」展开
- tags：10 个小红书标签，不带井号 = 品类大词（儿童绘本、睡前故事等）+ 场景词（睡前、亲子共读、哄睡等）+ 主题词（与本书行为问题相关）+ 1 个平台活动感话题
- cover_prompt：封面图绘图提示词，按以下规则生成——
  A. 原样包含下面的 Style Anchor，一个词都不许改：
  @@STYLE@@
  B. 封面骨架（图文式，必须照做）：米白纸纹底；顶部约四分之一区域放置超大描边中文标题——标题文字为书名号内的书名（不含书名号本身），黑色粗体配白色描边，居中、醒目、一字不差，**标题只渲染一次，绝不重复出现**；标题下方居中一行小字署名「图/文：阿苏的睡前故事」；中景 1 到 2 个角色（主角按本书书名确定）；简化场景（卧室、草地、浴室、餐桌四选一）。
  C. 出场角色必须使用下面角色设定表中的完整英文描述，逐字复用：
  @@CHARACTERS@@
  D. 提示词写法：画面描述用英文，文字渲染指令用中文，并用中文引号精确标出要渲染的标题与署名文字。除标题和署名外，画面不出现任何其他文字、字母或符号。"""

    STORY_PROMPT = """用户原始输入：
{input_query}

本期选题方案（JSON）：
{plan_output}

你是儿童睡前故事作家兼绘本分镜师。围绕选题方案中的 book_title 和 pain_point，创作 1 个**固定 6 段**的睡前故事，并为每段写一条场景提示词。

【故事质控红线，每条必须遵守】
1. 阿苏在场：主角阿苏贯穿全篇；配角只能从固定角色宇宙选择（妈妈、白白小兔、憨憨小熊、啾啾小鸟、橙橙小狐），不新造角色。
2. 儿童视角：用 3-6 岁孩子能懂的具体动作、声音和感受来写，不用抽象词语。
3. 不说教：道理藏在剧情里，结尾禁止出现「这个故事告诉我们」式总结。
4. 不恐怖：不出现怪兽、黑暗恐吓、抛弃威胁、医生打针吓唬等元素。
5. 节奏下行：情节从冲突到安抚，越到结尾越安静，最后一段必须是温暖入睡感的画面，适合哄睡。
6. 每段 1 到 2 句话、不超过 45 字，口语化，家长可直接朗读。文字要短——这段文字会原样压到插图上，超过 45 字排版必崩、渲染必错字。

【场景提示词规则（scene_prompt，英文，只写本段差异化内容）】
1. 只描述本段画面：出场角色（从下面角色设定表逐字复用其完整描述）+ 动作 + 场景 + 构图（中景为主、主体居中、留白充足）。
2. 图文逐句对齐：本段 story_text 中出现的角色和动作必须画出来；没有出现的角色禁止加入画面。这是同类账号最大的翻车点，必须守住。
3. 不要包含 Style Anchor、不要包含任何文字渲染指令——这些由下游统一拼接，写了就是浪费。
4. scene_prompt 控制在 80 词以内，宁可简洁不可堆砌。

【角色设定表】
@@CHARACTERS@@

【输出】
- style_anchor：原样复用下面这段 Style Anchor，全篇唯一，一个词都不许改：
@@STYLE@@
- paragraphs：固定 6 个段落对象，paragraph_id 必须恰好为 1、2、3、4、5、6，每个含 story_text（中文故事段落）和 scene_prompt（英文场景描述）。

【自检，必须执行】输出 JSON 之前先数一遍 paragraphs 数组长度：必须恰好为 6 个对象，少了就补齐到 6 段再输出，绝不许只交 1 段。"""

    COPY_PROMPT = """本期选题方案（JSON）：
{plan_output}

本期故事全文（JSON，含每段 story_text）：
{story_output}

你是小红书亲子博主「阿苏的睡前故事」的文案。你写的不是文学，是「给家长的讲读说明书」——家长收藏的不是故事，是今晚就能用的育儿脚本。

【正文模板（实测收藏率最高的干货结构）】
1. 开头栏目「📚教育意义」：用 pain_point 一句话戳痛点，然后两段式讲清这个故事帮家长解决什么、为什么讲道理没用而讲故事有用。
2. 主体栏目「🎈亲子共读干货｜3个方法」：把 core_points 展开成 3 条方法，每条 = 小标题 + 具体做法 + 一句可直接照念的示范话术（用引号标出，家长能照着读）。
3. 话术对比：全篇至少 2 处「不要说 X，可以说 Y」对比结构，这是收藏率的发动机，话术要口语、具体、今晚就能用。
4. 固定收尾句式：「你家宝贝也……吗？评论区告诉我吧～」（结合本书行为问题改写）。
5. 末尾另起一行放 10 个标签，用井号连接。

【约束】
- 正文（不含标签）600 字以内。
- 语气像隔壁有经验的妈妈，不端着、不说教、不用专业术语。
- 不出现 AI、生成、模型等字眼。
- 书名第一次出现时带书名号。

【输出】
copy_text：完整可直接发布的小红书正文（含末尾标签行）。"""

    for name in ("PLAN_PROMPT", "STORY_PROMPT", "COPY_PROMPT"):
        text = locals()[name]
        text = text.replace("@@STYLE@@", STYLE_ANCHOR).replace("@@CHARACTERS@@", CHARACTERS)
        locals()[name]  # no-op, 仅为可读性
        if name == "PLAN_PROMPT":
            PLAN_PROMPT = text
        elif name == "STORY_PROMPT":
            STORY_PROMPT = text
        else:
            COPY_PROMPT = text

    elements = [
        create_node("node_start", "start", "开始", 50, 250,
                    {"inputVariables": ["input_query"]}),
        create_node("node_plan", "llm", "① 选题策划", 320, 250, {
            "inputs": [{"name": "input_query", "type": "string", "source": ["node_start", "input_query"]}],
            "modelProfileCode": "deepseek-flash",
            "promptTemplate": PLAN_PROMPT,
            "outputFormat": "json",
            "jsonFields": [{"name": "output", "type": "object", "children": [
                {"name": "category", "type": "string", "description": "行为管教/生理习惯/情绪安抚", "children": []},
                {"name": "book_title", "type": "string", "description": "带书名号的书名", "children": []},
                {"name": "note_title", "type": "string", "description": "小红书笔记标题", "children": []},
                {"name": "pain_point", "type": "string", "description": "家长痛点一句话", "children": []},
                {"name": "core_points", "type": "array_string", "description": "3条教育要点", "children": []},
                {"name": "tags", "type": "array_string", "description": "10个标签，不带井号", "children": []},
                {"name": "cover_prompt", "type": "string", "description": "封面英文绘图提示词", "children": []},
            ]}],
            "outputVariable": "plan_output",
        }),
        create_node("node_story", "llm", "② 故事+内页提示词", 590, 250, {
            "inputs": [
                {"name": "input_query", "type": "string", "source": ["node_start", "input_query"]},
                {"name": "plan_output", "type": "string", "source": ["node_plan", "plan_output"]},
            ],
            "modelProfileCode": "deepseek-flash",
            "promptTemplate": STORY_PROMPT,
            "outputFormat": "json",
            "jsonFields": [{"name": "output", "type": "object", "children": [
                {"name": "style_anchor", "type": "string", "description": "全篇统一的风格锚点，原样复用", "children": []},
                {"name": "paragraphs", "type": "array_object", "description": "固定6段故事+场景提示词", "children": [
                    {"name": "paragraph_id", "type": "number", "description": "", "children": []},
                    {"name": "story_text", "type": "string", "description": "中文故事段落", "children": []},
                    {"name": "scene_prompt", "type": "string", "description": "英文场景描述，不含风格锚点和文字指令", "children": []},
                ]},
            ]}],
            "outputVariable": "story_output",
        }),
        create_node("node_copy", "llm", "③ 小红书正文", 860, 250, {
            "inputs": [
                {"name": "plan_output", "type": "string", "source": ["node_plan", "plan_output"]},
                {"name": "story_output", "type": "string", "source": ["node_story", "story_output"]},
            ],
            "modelProfileCode": "deepseek-flash",
            "promptTemplate": COPY_PROMPT,
            "outputFormat": "json",
            "jsonFields": [{"name": "output", "type": "object", "children": [
                {"name": "copy_text", "type": "string", "description": "可直接发布的完整正文", "children": []},
            ]}],
            "outputVariable": "copy_output",
        }),
        create_node("node_transform", "variable_transform", "提取段落数组", 1130, 250, {
            "inputs": [{"name": "story_output", "type": "string", "source": ["node_story", "story_output"]}],
            "input_variable": "{story_output}",
            "transform_type": "extract_json_path",
            "transform_args": {"path": "output.paragraphs"},
            "output_variable": "paragraphs_array",
        }),
        create_node("node_cover", "image_generator", "④ 封面图", 1400, 80, {
            "inputs": [{"name": "plan_output", "type": "string", "source": ["node_plan", "plan_output"]}],
            "modelProfileCode": "doubao-seedream-4-5-251128",
            "promptTemplate": "{plan_output.output.cover_prompt}",
            "size": "1728x2304",
            "optionsJson": "{\"watermark\": false}",
            "outputVariable": "cover_image_url",
        }),
        create_node("node_loop", "loop_controller", "⑤ 循环生成内页", 1400, 330, {
            "inputs": [{"name": "paragraphs_array", "type": "string", "source": ["node_transform", "paragraphs_array"]}],
            "arrayVariable": "{paragraphs_array}",
            "itemVariable": "paragraph",
            "outputVariable": "inner_images",
            "concurrency": 2,
        }),
        create_node("loop_body_group", "loop_body_group", "内页生图容器", 1400, 520,
                    {"controllerNodeId": "node_loop"},
                    style={"width": "420px", "height": "240px"}),
        create_node("node_inner_image", "image_generator", "内页插图", 40, 60, {
            "inputs": [
                {"name": "paragraph", "type": "string", "source": ["node_loop", "paragraph"]},
                {"name": "story_output", "type": "string", "source": ["node_story", "story_output"]},
            ],
            "modelProfileCode": "doubao-seedream-4-5-251128",
            # 以封面为参考图锁定全书画风与角色外观（__src 为厂商公网临时 URL，本地部署也能回源）
            "imageVariable": "cover_image_url__src",
            "promptTemplate": "{story_output.output.style_anchor}. 参考图仅用于统一画风和角色外观，绝不能复制参考图中的标题与署名文字。整幅画面必须是手绘蜡笔插画，绝不是照片，不是真人摄影。{paragraph.scene_prompt}. 画面底部严格保留约四分之一高度作为文字区：干净均匀的米白底色，以温暖的黑色手写体（马克笔质感）呈现中文文字「{paragraph.story_text}」，一字不差、只渲染一遍、绝不重复任何句子；文字 2 到 3 行、居中、字号统一且大小适中，不与画面主体重叠。除这段文字外，画面不出现任何其他文字、字母或符号。",
            "size": "1728x2304",
            "optionsJson": "{\"watermark\": false}",
            "outputVariable": "image_url",
        }, parent_node="loop_body_group", extent="parent"),
        create_node("node_end", "end", "结束", 1700, 250, {
            "outputFormat": "json",
            "outputFields": [
                {"name": "note_title", "type": "string", "value": "{plan_output.output.note_title}", "children": []},
                {"name": "book_title", "type": "string", "value": "{plan_output.output.book_title}", "children": []},
                {"name": "category", "type": "string", "value": "{plan_output.output.category}", "children": []},
                {"name": "tags", "type": "string", "value": "{plan_output.output.tags}", "children": []},
                {"name": "copy_text", "type": "string", "value": "{copy_output.output.copy_text}", "children": []},
                {"name": "cover_image", "type": "string", "value": "{cover_image_url}", "children": []},
                {"name": "inner_images", "type": "string", "value": "{inner_images}", "children": []},
                {"name": "story_paragraphs", "type": "string", "value": "{story_output.output.paragraphs}", "children": []},
            ],
        }),
        create_edge("node_start", "node_plan"),
        create_edge("node_plan", "node_story"),
        create_edge("node_story", "node_copy"),
        create_edge("node_copy", "node_transform"),
        create_edge("node_transform", "node_cover"),
        create_edge("node_cover", "node_loop"),
        create_edge("node_loop", "loop_body_group"),
        create_edge("loop_body_group", "node_end"),
    ]
    save_workflow(
        "11_小红书绘本内容流水线",
        "11_XHS_PictureBook_Pipeline.json",
        "输入话题/一段话 → 选题策划（五层漏斗）→ 睡前故事固定6段+场景提示词（Q1-Q10红线+角色宇宙，每段≤45字防压图排版崩坏）→ "
        "Gen3干货正文 → 封面图 → 循环内页图（以封面为参考图 imageVariable 锁全书画风与角色一致性，手绘蜡笔质感+反日漫/反照片负面词，"
        "文字只渲染一遍防重复句，optionsJson 关厂商水印）。模型：deepseek-flash 文案 / doubao-seedream-4-5-251128 生图 1728x2304 竖版",
        elements,
    )


if __name__ == "__main__":
    generate_01()
    generate_02()
    generate_03()
    generate_04()
    generate_05()
    generate_06()
    generate_07()
    generate_08()
    generate_09()
    generate_10()
    generate_11()
